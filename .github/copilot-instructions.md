After the code has been modified and the request from the user has been fulfilled, run `ty` and `ruff` to format the code and check for linting and typing errors:

```bash
uvx ty check
uvx ruff format
```
If either of these commands reports errors, fix them and run the command again until there are no errors.
