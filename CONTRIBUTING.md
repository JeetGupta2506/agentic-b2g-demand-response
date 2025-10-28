# Contributing to Agentic AI HEMS

Thank you for your interest in contributing to Agentic AI HEMS! This project aims to advance research in LLM-based energy management systems, and we welcome contributions from the community.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Types of Contributions](#types-of-contributions)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Research Collaboration](#research-collaboration)

---

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/agentic-ai-hems.git
   cd agentic-ai-hems
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Types of Contributions

We welcome various types of contributions:

### Code Contributions
- **New features**: Additional appliance types, scheduling algorithms, integration with other APIs
- **Bug fixes**: Corrections to existing functionality
- **Performance improvements**: Optimization of orchestrator logic, token efficiency
- **Documentation**: Code comments, docstrings, examples

### Research Contributions
- **Evaluation results**: Systematic model comparisons, performance benchmarks
- **New use cases**: Extensions to industrial settings, grid services, thermal flexibility
- **Algorithm improvements**: Better prompt engineering, novel orchestration patterns
- **Data analysis**: Insights from execution traces, statistical studies

### Documentation
- **Guides and tutorials**: Setup walkthroughs, configuration examples
- **API documentation**: Endpoint descriptions, parameter explanations
- **Architecture diagrams**: Visual representations of system design
- **Translation**: Documentation in other languages

### Issues and Discussions
- **Bug reports**: Detailed reports with reproduction steps
- **Feature requests**: Proposals for new functionality
- **Questions**: Help others by answering questions in issues

---

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- API keys (ENTSO-E, LLM provider)

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-api.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Running Locally

```bash
# Terminal 1: API server
python api.py

# Terminal 2: Dashboard server
python -m http.server 8000
```

Access dashboard at http://localhost:8000/dashboard.html

### Running Tests

```bash
# Test with cached reference prices
USE_CACHED_PRICES=true python orchestrator_agent_react.py "Schedule the dishwasher"

# Test with specific date
python -c "from tools import get_electricity_prices; print(get_electricity_prices(date='2025-10-15'))"

# Export results for analysis
python export_results_to_csv.py
```

---

## Code Style Guidelines

### Python

- **PEP 8**: Follow Python's style guide
- **Line length**: 100 characters maximum (not strict)
- **Docstrings**: Use Google-style docstrings for functions and classes
- **Type hints**: Add type hints for function signatures where possible
- **Imports**: Group standard library, third-party, and local imports separately

Example:
```python
def calculate_cost(prices: List[float], consumption: List[float]) -> float:
    """Calculate total energy cost from prices and consumption.

    Args:
        prices: List of electricity prices (EUR/MWh) for each time slot
        consumption: List of consumption values (kWh) for each time slot

    Returns:
        Total cost in EUR
    """
    return sum(p * c / 1000 for p, c in zip(prices, consumption))
```

### JavaScript (Dashboard)

- **Consistent formatting**: Use 2-space indentation
- **Clear variable names**: Descriptive names over abbreviations
- **Comments**: Explain non-obvious logic

### Markdown (Documentation)

- **Clear headings**: Use proper hierarchy (H1 for title, H2 for sections)
- **Code blocks**: Specify language for syntax highlighting
- **Links**: Use descriptive link text, not "click here"

---

## Testing

### Manual Testing

Before submitting a pull request:

1. **Test basic functionality**: Run at least one scheduling task end-to-end
2. **Check different appliances**: Test dishwasher, washing machine, EV charger
3. **Verify API endpoints**: Ensure `/api/models` and `/api/run/stream` work
4. **Test with your LLM provider**: Confirm compatibility

### Research Testing

For research contributions:

1. **Use reference prices**: Test with `test_prices_reference.json` for reproducibility
2. **Document parameters**: Log model name, temperature, max iterations
3. **Export results**: Use `export_results_to_csv.py` for analysis
4. **Compare baselines**: Run MILP baseline for comparison

---

## Submitting Changes

### Pull Request Process

1. **Update documentation**: Ensure README, docs, and code comments reflect your changes
2. **Test thoroughly**: Verify your changes work as expected
3. **Commit with clear messages**:
   ```bash
   git commit -m "Add support for heat pump scheduling"
   ```
4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Open a pull request**: Use the GitHub interface, provide clear description

### Pull Request Description Template

```markdown
## Description
Brief explanation of what this PR does and why.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement

## Testing
- [ ] Tested locally with [LLM provider]
- [ ] Tested with reference prices
- [ ] Verified API endpoints work
- [ ] Updated documentation

## Additional Notes
Any other context, screenshots, or relevant information.
```

### Commit Message Guidelines

- **Use imperative mood**: "Add feature" not "Added feature"
- **Be specific**: "Fix EV charger deadline parsing" not "Fix bug"
- **Reference issues**: "Fix #123: Resolve ENTSO-E timeout error"

---

## Reporting Issues

### Bug Reports

When reporting bugs, include:

1. **Description**: What happened vs. what you expected
2. **Reproduction steps**: Detailed steps to reproduce the issue
3. **Environment**:
   - Python version
   - Operating system
   - LLM provider and model
   - Docker or local setup
4. **Logs**: Relevant error messages or execution traces
5. **Screenshots**: If applicable (e.g., dashboard issues)

### Feature Requests

When proposing features:

1. **Use case**: Describe the problem this feature would solve
2. **Proposed solution**: How you envision the feature working
3. **Alternatives**: Other approaches you considered
4. **Research context**: How this relates to energy management research

---

## Research Collaboration

### Academic Use

If you're using this project for research:

- **Cite the work**: Citation details will be added upon publication
- **Share results**: Consider contributing evaluation results back
- **Collaborate**: Reach out for potential research collaboration

### Data Sharing

If you have valuable datasets or evaluation results:

1. **Anonymize**: Remove any sensitive information
2. **Document**: Provide clear metadata (date range, location, parameters)
3. **Format**: Use CSV or JSON for easy integration
4. **License**: Clarify data usage rights

---

## Questions?

- **Issues**: Open an issue on GitHub for questions or discussions
- **Email**: Contact Reda El Makroum at elmakroum@eeg.tuwien.ac.at

---

Thank you for contributing to advancing LLM-based energy management research!
