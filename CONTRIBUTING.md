# Contributing to wp_chariot

Thank you for your interest in contributing to wp_chariot! This guide will help you get started with contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Workflow](#workflow)
- [Pull Requests](#pull-requests)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Refactoring Priorities](#refactoring-priorities)

## Code of Conduct

By participating in this project, you agree to abide by our code of conduct:

- Be respectful and inclusive of all contributors
- Provide constructive feedback and criticism
- Focus on the best possible outcome for the project's users
- Show empathy towards other community members

## Getting Started

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/wp_chariot.git
   cd wp_chariot
   ```

3. Add the original repository as upstream:
   ```bash
   git remote add upstream https://github.com/aficiomaquinas/wp_chariot.git
   ```

### Setting Up Your Environment

1. Install dependencies:
   ```bash
   cd python
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development requirements
   ```

2. Create test configuration:
   ```bash
   cp config.example.yaml config.yaml
   cp sites.example.yaml sites.yaml
   ```

## Development Environment

### Recommended Tools

- **Editor**: VSCode with Python and YAML extensions
- **Python Version Manager**: asdf or pyenv
- **Virtual Environment**: venv or conda
- **Linting**: flake8, pylint
- **Formatting**: black

### Environment Setup

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dev dependencies
pip install -r requirements-dev.txt
```

## Workflow

### Branching Strategy

We follow a simplified git flow approach:

- `main` branch contains stable code
- Feature branches are created from `main`
- Use descriptive branch names with prefixes:
  - `feature/` for new features
  - `fix/` for bug fixes
  - `refactor/` for code improvements
  - `docs/` for documentation changes

Example:
```bash
git checkout -b feature/improve-patch-system
```

### Development Cycle

1. **Update your fork**:
   ```bash
   git checkout main
   git pull upstream main
   ```

2. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make changes and commit**:
   ```bash
   git add .
   git commit -m "Your descriptive commit message"
   ```

4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a pull request** via GitHub UI

## Pull Requests

### Pull Request Guidelines

1. **Title**: Use a clear, descriptive title
2. **Description**: Include:
   - What changes you've made
   - Why you've made them
   - Any related issues
   - Steps to test the changes
3. **Keep PRs focused**: Each PR should address a single concern
4. **Update documentation**: If your changes affect behavior or user interaction
5. **Add tests**: For new features or bug fixes

### Review Process

1. At least one core maintainer must review and approve
2. CI checks must pass
3. PR should be mergeable without conflicts
4. Follow up on reviewer feedback promptly

## Coding Standards

We follow PEP 8 with some modifications:

### Python Style Guide

- **Line Length**: 88 characters (Black default)
- **Indentation**: 4 spaces
- **Naming**:
  - Classes: `PascalCase`
  - Functions/Methods: `snake_case`
  - Variables: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
- **Docstrings**: Google style

### Code Quality

- Use type hints where possible
- Write meaningful docstrings
- Keep functions small and focused
- Follow the principle of least surprise

### Tools

- **Black**: For code formatting
  ```bash
  black python/
  ```

- **Flake8**: For linting
  ```bash
  flake8 python/
  ```

## Testing

### Test Structure

Tests are located in the `tests/` directory and follow this structure:
```
tests/
├── conftest.py       # Shared fixtures
├── test_patch.py     # Tests for patch functionality
├── test_sync.py      # Tests for sync functionality
└── ...
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_patch.py

# Run with coverage
pytest --cov=python
```

### Writing Tests

- Each module should have corresponding tests
- Focus on unit tests for core functionality
- Use mocks for external dependencies
- Include both positive and negative test cases

## Documentation

### Code Documentation

- All public functions and classes should have docstrings
- Include type hints for parameters and return values
- Document exceptions that may be raised

Example:
```python
def sync_files(site: str, direction: str = "from-remote", dry_run: bool = False) -> bool:
    """Synchronize files between local and remote environments.
    
    Args:
        site: The site name as configured in sites.yaml
        direction: Direction of synchronization, either "from-remote" or "to-remote"
        dry_run: If True, only show what would be done without making changes
        
    Returns:
        True if synchronization was successful, False otherwise
        
    Raises:
        ConfigError: If site configuration is invalid
        SSHError: If SSH connection fails
    """
    # Implementation
```

### User Documentation

- Update README.md for major changes
- Update or add documentation in the `docs/` directory
- Include examples for new features

## Refactoring Priorities

wp_chariot has identified several refactoring priorities that contributors can help with:

### 1. Circular Dependencies

Current issue: `config_yaml.py` and `utils/filesystem.py` have a circular dependency.

Potential approach:
- Refactor `create_backup()` to accept a list of protected files
- Create a dedicated configuration interface

### 2. Large Files

Several files exceed 500 lines and need splitting:
- `commands/patch.py` (1410 lines)
- `config_yaml.py` (857 lines)
- `commands/database.py` (743 lines)
- `cli.py` (714 lines)
- `commands/sync.py` (686 lines)
- `utils/wp_cli.py` (622 lines)

### 3. Duplicated Code

There's duplicated logic for:
- SSH/DDEV execution
- Command execution patterns
- WP-CLI commands

### 4. Configuration Management

Improvements needed:
- Centralize configuration-related logic
- Create clean separation between configuration and utilities
- Implement proper configuration interfaces

## Questions?

If you have any questions about contributing, please open an issue on GitHub or reach out to the maintainers.

Thank you for contributing to wp_chariot! 