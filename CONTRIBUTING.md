# Contributing to reeleezee-exporter

Thank you for considering contributing to this project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/reeleezee-exporter.git`
3. Install in development mode: `pip install -e ".[web]"`
4. Create a feature branch: `git checkout -b feature/my-feature`

## Development

### Running tests

```bash
pip install pytest
pytest tests/ -v
```

### Linting

```bash
pip install flake8
flake8 src/ --max-line-length=120
flake8 web/ --max-line-length=120
```

### Running the web UI locally (Docker)

```bash
cd docker
docker compose up --build
```

## Code Guidelines

- Follow existing code style and patterns
- Add tests for new functionality
- Keep commits focused and descriptive
- No credentials or sensitive data in code

## Pull Requests

1. Ensure all tests pass
2. Update documentation if needed
3. Describe what your PR does and why
4. Reference any related issues

## Reporting Issues

- Use the GitHub issue tracker
- Include steps to reproduce
- Include relevant error messages or logs
- Mention your Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
