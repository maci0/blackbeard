# Tool Examples

WASM tooling is supported. See `deploy/wit/tool.wit` for the interface specification.
WASM tools must export `run(input: string) -> tool-result` and optionally `describe() -> string`.

No example `.wasm` modules are included yet. The sandbox runtime (`blackbeard.engine.sandbox`) is implemented — contribute examples by compiling a Rust/C/Go module against the WIT interface above.
