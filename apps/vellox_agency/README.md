### Vellox Agency

Open source ERP for media agencies. Part of [Vellox ERP Next](https://github.com/bhamalawi-alt/Vellox-ERP-Next).

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/bhamalawi-alt/Vellox-ERP-Next --branch version-15
bench install-app vellox_agency
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/vellox_agency
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
