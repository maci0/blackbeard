"""Flow execution: runs multi-step Flow resources sequentially.

Step types: crew, function, router, condition, transform.
Public helpers: ``evaluate_condition``, ``resolve_dotted``, ``call_hook``.
"""

from __future__ import annotations

import importlib
import logging
import math
import operator
from typing import Any

from blackbeard.resources import (
    ALLOWED_CALLABLE_MODULE_PREFIXES,
    BLOCKED_CALLABLE_MODULES,
)

__all__ = [
    "call_hook",
    "evaluate_condition",
    "resolve_dotted",
    "run_flow_steps",
]

from blackbeard.engine.loader import LoaderError, ResourceLoader

_CONDITION_OPS: tuple[tuple[str, Any], ...] = (
    (">=", operator.ge),
    ("<=", operator.le),
    ("!=", operator.ne),
    ("==", operator.eq),
    (">", operator.gt),
    ("<", operator.lt),
)

logger = logging.getLogger(__name__)


def call_hook(
    loader: ResourceLoader,
    hook_path: str,
    arg: Any,
    hook_name: str,
) -> None:
    """Resolve and call a hook callable, logging warnings on failure."""
    try:
        fn = loader.import_callable(hook_path)
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
    except Exception as exc:
        logger.warning(
            "Hook '%s' raised an exception: %s",
            hook_name,
            hook_path,
            exc_info=True,
            extra={
                "event": "hook_execution_failed",
                "hook_name": hook_name,
                "hook_path": hook_path,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            },
        )


def _validate_callable_path(
    fn_path: str,
    step_name: str,
    flow_name: str,
) -> str | None:
    """Check fn_path against blocked/allowed module lists.

    Returns an error string if blocked, or ``None`` if the path is allowed.
    """
    module_path = fn_path.rsplit(":", 1)[0]
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
        return "error: blocked module"
    if not fn_path.startswith(ALLOWED_CALLABLE_MODULE_PREFIXES):
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
        return "error: function not in allowlist"
    return None


def _load_callable(fn_path: str) -> Any:
    """Import and return the callable referenced by ``module.path:func_name``."""
    if ":" not in fn_path:
        raise LoaderError(f"Invalid callable path (expected 'module:func'): {fn_path}")
    module_path, fn_name = fn_path.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, fn_name)


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
    total_steps = len(steps)

    for step_index, step in enumerate(steps):
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
            failed_deps = [
                k for k, v in step_outputs.items() if isinstance(v, str) and v.startswith("error:")
            ]
            if failed_deps:
                logger.warning(
                    "Flow step '%s' receives error outputs from steps %s — "
                    "downstream results may be unreliable",
                    step_name,
                    failed_deps,
                    extra={
                        "event": "flow_step_error_propagation",
                        "flow_name": flow_name,
                        "step_name": step_name,
                        "failed_dependencies": failed_deps,
                    },
                )
            step_inputs = {**inputs, **step_outputs}

            if step_hooks.get("before"):
                call_hook(loader, step_hooks["before"], step_inputs, f"step:{step_name}:before")

            try:
                result = crew.kickoff(inputs=step_inputs)
            except Exception as step_exc:
                if step_hooks.get("on_error"):
                    call_hook(
                        loader,
                        step_hooks["on_error"],
                        step_exc,
                        f"step:{step_name}:on_error",
                    )
                raise

            if isinstance(result, CrewOutput):
                step_outputs[step_name] = result.raw
            else:
                step_outputs[step_name] = str(result) if result else ""
            last_result = result

            if step_hooks.get("after"):
                call_hook(loader, step_hooks["after"], last_result, f"step:{step_name}:after")

            logger.info(
                "Flow step '%s' completed (crew=%s, step %d/%d)",
                step_name,
                crew_ref,
                step_index + 1,
                total_steps,
                extra={
                    "event": "flow_step_completed",
                    "flow_name": flow_name,
                    "step_name": step_name,
                    "crew_ref": crew_ref,
                    "step_index": step_index,
                    "total_steps": total_steps,
                },
            )

        elif step_type == "function":
            fn_path = step.get("function_path", "")
            if fn_path and ":" in fn_path:
                block_err = _validate_callable_path(fn_path, step_name, flow_name)
                if block_err:
                    step_outputs[step_name] = block_err
                else:
                    try:
                        fn = _load_callable(fn_path)
                        step_result = fn({**inputs, **step_outputs})
                        step_outputs[step_name] = step_result
                    except Exception as exc:
                        logger.error(
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
                        step_outputs[step_name] = f"error: {type(exc).__name__}"

        elif step_type == "router":
            fn_path = step.get("function_path", "")
            routes = step.get("routes", {})
            if fn_path and ":" in fn_path:
                block_err = _validate_callable_path(fn_path, step_name, flow_name)
                if block_err:
                    step_outputs[step_name] = block_err
                else:
                    try:
                        fn = _load_callable(fn_path)
                        route_key = str(fn({**inputs, **step_outputs}))
                        step_outputs[step_name] = route_key
                        next_step = routes.get(route_key)
                        if next_step:
                            logger.info(
                                "Router '%s' chose route '%s' → '%s'",
                                step_name,
                                route_key,
                                next_step,
                                extra={
                                    "event": "flow_router_resolved",
                                    "flow_name": flow_name,
                                    "step_name": step_name,
                                    "route_key": route_key,
                                    "next_step": next_step,
                                },
                            )
                        else:
                            logger.warning(
                                "Router '%s' returned unknown route: %s",
                                step_name,
                                route_key,
                                extra={
                                    "event": "flow_router_unknown_route",
                                    "flow_name": flow_name,
                                    "step_name": step_name,
                                    "route_key": route_key,
                                    "available_routes": sorted(routes.keys()),
                                },
                            )
                    except Exception as exc:
                        logger.warning(
                            "Router step '%s' failed: %s",
                            step_name,
                            exc,
                            exc_info=True,
                            extra={
                                "event": "flow_router_step_failed",
                                "flow_name": flow_name,
                                "step_name": step_name,
                                "error_type": type(exc).__name__,
                            },
                        )
                        step_outputs[step_name] = f"error: router {type(exc).__name__}"

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
                    extra={
                        "event": "flow_condition_evaluated",
                        "flow_name": flow_name,
                        "step_name": step_name,
                        "route_key": route_key,
                        "next_step": next_step,
                    },
                )

        elif step_type == "transform":
            wasm_ref = step.get("wasm_module")
            if wasm_ref:
                try:
                    import json as _json

                    from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

                    sandbox = WasmSandbox()
                    transform_input = _json.dumps({**inputs, **step_outputs})
                    wasm_result = sandbox.invoke(wasm_ref, transform_input)
                    step_outputs[step_name] = (
                        _json.loads(wasm_result.output) if wasm_result.output else {}
                    )
                except Exception as exc:
                    logger.error(
                        "Transform step '%s' failed: %s",
                        step_name,
                        exc,
                        exc_info=True,
                        extra={
                            "event": "flow_transform_step_failed",
                            "flow_name": flow_name,
                            "step_name": step_name,
                            "wasm_module": wasm_ref,
                            "error_type": type(exc).__name__,
                        },
                    )
                    step_outputs[step_name] = "error: step failed"
            else:
                logger.warning(
                    "Transform step '%s' has no wasm_module — skipped",
                    step_name,
                    extra={
                        "event": "flow_step_skipped",
                        "flow_name": flow_name,
                        "step_name": step_name,
                        "reason": "no_wasm_module",
                    },
                )

        else:
            logger.warning(
                "Flow step '%s' has unknown type '%s' — skipped",
                step_name,
                step_type,
                extra={
                    "event": "flow_step_unknown_type",
                    "flow_name": flow_name,
                    "step_name": step_name,
                    "step_type": step_type,
                    "step_index": step_index,
                },
            )
            step_outputs[step_name] = f"error: unknown step type '{step_type}'"

    completed_steps = [
        s.get("name", "unnamed") for s in steps if s.get("name", "unnamed") in step_outputs
    ]
    failed_steps = [
        name
        for name in completed_steps
        if isinstance(step_outputs.get(name), str) and step_outputs[name].startswith("error:")
    ]
    if failed_steps:
        logger.warning(
            "Flow '%s' completed with %d/%d steps in error state: %s",
            flow_name,
            len(failed_steps),
            total_steps,
            failed_steps,
            extra={
                "event": "flow_completed_with_errors",
                "flow_name": flow_name,
                "total_steps": total_steps,
                "completed_steps": len(completed_steps),
                "failed_steps": failed_steps,
            },
        )
    else:
        logger.info(
            "Flow '%s' completed: %d/%d steps produced output",
            flow_name,
            len(completed_steps),
            total_steps,
            extra={
                "event": "flow_completed",
                "flow_name": flow_name,
                "total_steps": total_steps,
                "completed_steps": len(completed_steps),
            },
        )
    return last_result


def evaluate_condition(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a simple condition expression safely (NO eval/exec).

    Supports: key comparisons like "score > 0.8", "status == completed",
    key existence like "error in outputs", and boolean keys.
    """
    expr = expr.strip()

    for op, fn in _CONDITION_OPS:
        if op in expr:
            left, right = expr.split(op, 1)
            left_val = resolve_dotted(left.strip().strip("'\""), context)
            right_str = right.strip().strip("'\"")
            right_val: float | str
            try:
                right_val = float(right_str)
                if math.isinf(right_val) or math.isnan(right_val):
                    right_val = right_str
            except ValueError:
                right_val = right_str
            try:
                return bool(fn(left_val, right_val))
            except TypeError:
                logger.debug(
                    "Condition type mismatch: %r (%s) %s %r (%s) — evaluating as False",
                    left_val,
                    type(left_val).__name__,
                    op,
                    right_val,
                    type(right_val).__name__,
                    extra={
                        "event": "condition_type_mismatch",
                        "operator": op,
                        "left_type": type(left_val).__name__,
                        "right_type": type(right_val).__name__,
                    },
                )
                return False

    if " in " in expr:
        key, container = expr.split(" in ", 1)
        container_val = resolve_dotted(container.strip(), context)
        if isinstance(container_val, (dict, list, str)):
            return key.strip().strip("'\"") in container_val
        return False

    val = resolve_dotted(expr, context)
    return bool(val)


_MAX_RESOLVE_DEPTH = 20


def resolve_dotted(path: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted path like 'outputs.score' against a context dict."""
    parts = path.split(".")
    if len(parts) > _MAX_RESOLVE_DEPTH:
        return None
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current
