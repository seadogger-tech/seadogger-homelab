# HDHomeRun Guide Utility

A small Python utility that pulls the HDHomeRun XMLTV guide using the network device to pull the DeviceAuth code and then query the HDHomerun API. The guide is saved locally.
If no `--target` is supplied, the script saves the file as **xmltv.xml** in the directory where the script is executed.

## Features

- **Configurable discovery endpoint** – point the script at any HDHomeRun device.
- **Configurable target** – write the XML to a local file. If `--target` is omitted, the guide is saved as `xmltv.xml` in the current working directory.
- No external Python dependencies – uses only the standard library.

## Location

The script lives in the repository under:

```
seadogger-homelab-pro/core/useful_scripts/fetch_hdhomerun_guide.py
```

## Prerequisites

- Python 3.8+ (the script uses `urllib` and `argparse` from the stdlib).

## Installation

```bash
# Copy the script into a directory of your choice
cp fetch_hdhomerun_guide.py /desired/location/
chmod +x /desired/location/fetch_hdhomerun_guide.py
```

## Usage

### A️ Default (no target)

```bash
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json
```

The guide will be saved as `xmltv.xml` in the directory where you run the command.

### B️ Store locally (explicit path)

```bash
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json \
    --target /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
```


## Help

Run the script with `-h` or `--help` to see the full list of options:

```bash
./fetch_hdhomerun_guide.py --help
```

## License

This script is provided under the MIT License. Feel free to modify and adapt it to your needs.
