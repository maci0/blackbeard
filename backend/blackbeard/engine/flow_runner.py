"""Flow execution: runs multi-step Flow resources sequentially.

Extracted from executor.py to reduce module size and improve cohesion.
Handles step types: crew, function, router, condition, transform.
"""

from __future__ import annotations

import logging
from typing import Any

from blackbeard.engine.loader import LoaderError, ResourceLoader

logger = logging.getLogger(__name__)


def _call_hook(
    loader: ResourceLoader,
    hook_path: str,
    arg: Any,
    hook_name: str,
) -> None:
    """Resolve and call a hook callable, logging warnings on failure."""
    try:
        fn = loader._import_callable(hook_path)
        if fn is not None:
            fn(arg)
            logger.info(
                "Hook '%s' executed: %s",
                hook_name,
                hook_path,
                extra={
                    "event": "hook_executed",
                    "hook_name": hook_name,
                    "hook_path": hook_path,
                },
            )
        else:
            logger.warning(
                "Hook '%s' could not be imported: %s",
                hook_name,
                hook_path,
                extra={
                    "event": "hook_import_failed",
                    "hook_name": hook_name,
                    "hook_path": hook_path,
                },
            )
    except Exception:
        logger.warning(
            "Hook '%s' raised an exception: %s",
            hook_name,
            hook_path,
            exc_info=True,
            extra={
                "event": "hook_execution_failed",
                "hook_name": hook_name,
                "hook_path": hook_path,
            },
        )


def run_flow_steps(
    loader: Any,
    resource_snapshot: dict[str, dict[str, Any]],
    flow_name: str,
    inputs: dict[str, Any],
    listener: Any,
) -> Any:
    """Execute a Flow resource by running its steps sequentially.

    Each step of type "crew" builds and kicks off the referenced crew.
    Step outputs are chained: the result of step N is available to step N+1.
    """
    from crewai.crews.crew_output import CrewOutput

    flow_snap = resource_snapshot.get(f"Flow/{flow_name}")
    if not flow_snap:
        raise LoaderError(f"Flow '{flow_name}' not found in resource snapshot")

    flow_spec = flow_snap.get("spec", {})
    steps = flow_spec.get("steps", [])
    step_outputs: dict[str, Any] = {}
    last_result: Any = None

    for step in steps:
        step_name = step.get("name", "unnamed")
        step_type = step.get("type", "crew")
        step_hooks = step.get("hooks", {})

        if step_type == "crew":
            crew_ref = step.get("crew")
            if not crew_ref:
                logger.warning(
                    "Flow step '%s' has no crew ref — skipped",
                    step_name,
                    extra={
                        "event": "flow_step_skipped",
                        "flow_name": flow_name,
                        "step_name": step_name,
                        "reason": "no_crew_ref",
                    },
                )
                continue

            crew = loader.build_crew(crew_ref.split("/")[-1] if "/" in crew_ref else crew_ref)
            step_inputs = {**inputs, **step_outputs}

            if step_hooks.get("before"):
                _call_hook(loader, step_hooks["before"], step_inputs, f"step:{step_name}:before")

            try:
                result = crew.kickoff(inputs=step_inputs)
            except Exception as step_exc:
                if step_hooks.get("on_error"):
                    _call_hook(
                        loader,
                        step_hooks["on_error"],
                        step_exc,
                        f"step:{step_name}:on_error",
                    )
                raise

            if isinstance(result, CrewOutput):
                step_outputs[step_name] = result.raw
                last_result = result
            else:
                step_outputs[step_name] = str(result) if result else ""
                last_result = result

            if step_hooks.get("after"):
                _call_hook(loader, step_hooks["after"], last_result, f"step:{step_name}:after")

            logger.info(
                "Flow step '%s' completed (crew=%s)",
                step_name,
                crew_ref,
                extra={
                    "event": "flow_step_completed",
                    "flow_name": flow_name,
                    "step_name": step_name,
                    "crew_ref": crew_ref,
                },
            )

        elif step_type == "function":
            fn_path = step.get("function_path", "")
            if fn_path and ":" in fn_path:
                module_path, fn_name = fn_path.rsplit(":", 1)
                from blackbeard.resources import (
                    ALLOWED_CALLABLE_MODULE_PREFIXES,
                    BLOCKED_CALLABLE_MODULES,
                )

                top_module = module_path.split(".")[0]
                if top_module in BLOCKED_CALLABLE_MODULES:
                    logger.warning(
                        "Flow step '%s' blocked: module '%s' is not allowed",
                        step_name,
                        top_module,
                        extra={
                            "event": "flow_step_blocked",
                            "flow_name": flow_name,
                            "step_name": step_name,
                            "blocked_module": top_module,
                        },
                    )
                    step_outputs[step_name] = "error: blocked module"
                elif not fn_path.startswith(ALLOWED_CALLABLE_MODULE_PREFIXES):
                    logger.warning(
                        "Flow step '%s' blocked: function_path '%s' not in allowlist",
                        step_name,
                        fn_path,
                        extra={
                            "event": "flow_step_blocked",
                            "flow_name": flow_name,
                            "step_name": step_name,
                            "function_path": fn_path,
                        },
                    )
                    step_outputs[step_name] = "error: function not in allowlist"
                else:
                    try:
                        import importlib

                        mod = importlib.import_module(module_path)
                        fn = getattr(mod, fn_name)
                        step_result = fn({**inputs, **step_outputs})
                        step_outputs[step_name] = step_result
                    except Exception as exc:
                        logger.warning(
                            "Flow function step '%s' failed: %s",
                            step_name,
                            exc,
                            exc_info=True,
                            extra={
                                "event": "flow_function_step_failed",
                                "flow_name": flow_name,
                                "step_name": step_name,
                                "function_path": fn_path,
                                "error_type": type(exc).__name__,
                            },
                        )
                        step_outputs[step_name] = "error: step execution failed"

        elif step_type == "router":
            fn_path = step.get("function_path", "")
            routes = step.get("routes", {})
            if fn_path and ":" in fn_path:
                fn = ResourceLoader._import_callable(fn_path)
                if fn:
                    try:
                        route_key = str(fn({**inputs, **step_outputs}))
                        step_outputs[step_name] = route_key
                        next_step = routes.get(route_key)
                        if next_step:
                            logger.info(
                                "Router '%s' chose route '%s' → '%s'",
                                step_name,
                                route_key,
                                next_step,
                            )
                        else:
                            logger.warning(
                                "Router '%s' returned unknown route: %s",
                                step_name,
                                route_key,
                            )
                    except Exception as exc:
                        logger.warning("Router step '%s' failed: %s", step_name, exc)
                        step_outputs[step_name] = f"error: {type(exc).__name__}"

        elif step_type == "condition":
            condition = step.get("condition", "")
            routes = step.get("routes", {})
            if condition:
                result = evaluate_condition(condition, {**inputs, **step_outputs})
                route_key = "true" if result else "false"
                step_outputs[step_name] = result
                next_step = routes.get(route_key)
                logger.info(
                    "Condition '%s' evaluated to %s → '%s'",
                    step_name,
                    route_key,
                    next_step or "(no route)",
                )

        elif step_type == "transform":
            wasm_ref = step.get("wasm_module")
            if wasm_ref:
                try:
                    import json as _json

                    from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

                    sandbox = WasmSandbox()
                    transform_input = _json.dumps({**inputs, **step_outputs})
                    wasm_result = sandbox.execute(wasm_ref, transform_input)
                    step_outputs[step_name] = (
                        _json.loads(wasm_result.output) if wasm_result.output else {}
                    )
                except Exception as exc:
                    logger.warning("Transform step '%s' failed: %s", step_name, exc)
                    step_outputs[step_name] = f"error: {type(exc).__name__}"
            else:
                logger.warning("Transform step '%s' has no wasm_module — skipped", step_name)

    return last_result


def evaluate_condition(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a simple condition expression safely (NO eval/exec).

    Supports: key comparisons like "score > 0.8", "status == completed",
    key existence like "error in outputs", and boolean keys.
    """
    expr = expr.strip()

    for op, fn in [
        (">=", lambda a, b: a >= b),
        ("<=", lambda a, b: a <= b),
        ("!=", lambda a, b: a != b),
        ("==", lambda a, b: a == b),
        (">", lambda a, b: a > b),
        ("<", lambda a, b: a < b),
    ]:
        if op in expr:
            left, right = expr.split(op, 1)
            left_val = resolve_dotted(left.strip().strip("'\""), context)
            right_str = right.strip().strip("'\"")
            try:
                right_val = float(right_str)
            except ValueError:
                right_val = right_str
            try:
                return bool(fn(left_val, right_val))
            except TypeError:
                return False

    if " in " in expr:
        key, container = expr.split(" in ", 1)
        container_val = resolve_dotted(container.strip(), context)
        if isinstance(container_val, (dict, list, str)):
            return key.strip().strip("'\"") in container_val
        return False

    val = resolve_dotted(expr, context)
    return bool(val)


def resolve_dotted(path: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted path like 'outputs.score' against a context dict."""
    parts = path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current
