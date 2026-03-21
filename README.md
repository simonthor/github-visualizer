# Github Contributions Visualizer
Visualize **all** the Github contributions of any Github user with a simple command line tool. The tool generates an SVG file that can be easily shared or embedded in websites.

On the Github website, only the contributions from one year are visible. This tool allows you to see the contributions from all years in a single SVG file.
The colors are normalized to the maximum contributions in a single day over the whole period that a user has been active, so the colors are comparable across years.

## Installation
You can install the tool using pip:
```bash
pip install git+https://github.com/simonthor/github-visualizer.git
```
or run it directly with `uvx`, `pipx` or similar tools:
```bash
uvx git+https://github.com/simonthor/github-visualizer.git
```

## Usage
To generate an SVG file for a specific Github user, run the following command:
```bash
github-visualizer <github_username> --output <output_file.svg>
```
Additional options include:
- `--start-year <year>`: Specify the starting year for the contributions (default is the earliest year of contributions).
- `--end-year <year>`: Specify the ending year for the contributions (default is the latest year of contributions).

## Example
To visualize the contributions of the user `simonthor` and save it as `simonthor-contributions.svg`, you would run:
```bash
github-visualizer simonthor --output simonthor-contributions.svg
```

