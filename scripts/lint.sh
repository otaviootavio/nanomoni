mypy src tests
mypy bench-plotter
ruff check src tests bench-plotter --fix
ruff format src tests bench-plotter
