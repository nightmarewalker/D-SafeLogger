## Checklist

### Tests
- [ ] `uv run pytest tests -q` passes.
- [ ] New/changed code has corresponding tests.

### Examples / docs
- [ ] I changed no `examples/*.md` executable workflow.
- [ ] Or I updated the matching `tests/examples/test_*.py`.
- [ ] Or the code block is explicitly docs-only / illustrative / external-service dependent.

### Type checks
- [ ] `uv run mypy src` passes.
- [ ] `uv run pyright src` passes.
