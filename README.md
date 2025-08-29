

### Managing secrets
We are not using `.env` files but rather `env.sh` files that export the variables as environment variables.

They are defined in `/envs/**`. We also provide an example that contains dummy text. To quickstart the project, copy and paste the content into `./envs/env.sh`.

### Running with Python for development

Use Poetry for managing packages and pyenv for managing Python versions.

- Reference for pyenv: https://github.com/pyenv/pyenv
- Reference for Poetry: https://python-poetry.org/docs/managing-environments/

We are using Python 3.9.25, so run:

```bash
poetry env use python3.9.25
```

To add the interpreter to VS Code:
```bash
poetry env info --path
```

Then add the path to `Python: Select Interpreter` visible in the command palette (Ctrl+Shift+P or Cmd+Shift+P on macOS).

After all these steps, to run the code:
```bash
./entrypoint.sh
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