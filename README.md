

### Managing secrets
We are not using `.env` files but rather `env.sh` files that export the variables as environment variables.

They are defined in `/envs/**`. We also provide an example that contains dummy text. To quickstart the project, copy and paste the content into `./envs/env.sh`.

### Running with Python for development

Use Poetry for managing packages and pyenv for managing Python versions.

- Reference for pyenv: https://github.com/pyenv/pyenv
- Reference for Poetry: https://python-poetry.org/docs/managing-environments/

We are using Python 3.9, so run:

```bash
pyenv install 3.9
```

```bash
pyenv local 3.9
```

```bash
poetry env use python3.9
```

To add the interpreter to VS Code:
```bash
poetry env info --path
```

Then add the path to `Python: Select Interpreter` visible in the command palette (Ctrl+Shift+P or Cmd+Shift+P on macOS).


### Generate the envs
Then, create the envs
```bash
envs/issuer-env.example.sh
```

```bash
envs/vendor-env.example.sh
```

```bash
envs/client-env.example.sh
```

### Start the DBs
```bash
docker compose up redis-vendor redis-issuer -d
```

### Run the scripts
For each step below, run in a new terminal.

First, run the issuer
```bash
./scripts/issuer-entrypoint.sh
```

Then, run the vendor
```bash
./scripts/vendor-entrypoint.sh
```

Finally, run the client.
```bash
./scripts/client-entrypoint.sh
```

### Running with Docker 

```bash
docker build . -t  nanomoni
```

```bash
# 1. Source the environment variables
. ./envs/env.sh 

# 2. Verify the variable is set (this is correct)
echo ${SECRET} 

# 3. Run Docker with the environment variable
docker run -e SECRET=$SECRET nanomoni
```

### Linter
```bash
ruff format src/
```

```bash
ruff check src/
```

### Static checker
```bash
mypy src/
```

# TODO
- [] Add cAdvisor + Prometheus + Graphana
- [x] Create Kerner component UML
- [x] Create Issuer component UML
- [x] Create Client component UML
- [x] Create System data flow overview UML
- [x] Create Phase 1 / setup UML
- [x] Create Phase 2 / payments UML
- [x] Create Phase 3 / close sequence diagram UML