# Contributing

Use synthetic data in examples and tests. Never commit credentials, personal
information, production logs, Terraform state, or local document stores.

Create a Python virtual environment and install `requirements-dev.lock`.
Run `python -m unittest discover -s tests -v` before opening a pull request.
Add regression tests for behavioral changes and update the API examples when
contracts change. Keep changes within the existing stack.

`requirements.txt` lists direct runtime dependencies; `requirements.lock` pins
the complete runtime environment. `requirements-dev.lock` additionally pins the
HTTP test client where used. Update both lock files when dependencies change,
run the tests, and audit with `python -m pip_audit -r requirements-dev.lock`.
The CI workflow does not deploy infrastructure or publish container images.
