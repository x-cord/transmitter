# transmitter
Mass Usenet uploads with ParPar and Nyuu, built for reliability and fault-tolerance.

![circle-small](https://github.com/x-cord/transmitter/assets/42466980/7e5b5538-07aa-4905-b3f6-ffd65aa85a84)

## Requirements
- Python 3.11
- [ParPar](https://github.com/animetosho/ParPar)
- [Nyuu (x-cord fork)](https://github.com/x-cord/Nyuu)

## Initial setup
Install Python dependencies with `pip install -r requirements.txt`.  
Fill in your account(s), posting params, locations to upload, and work directories. Adjust split size, add extra filtering if desired.

## Usage
Launch `transmitter.py`. Make sure there is only one instance of the program running.  
It will go through all locations, generate parity files, and upload files to all specified accounts.  
Failed articles are saved to be reposted in future runs, generated nzbs are checked for errors.  
The script is able to pick up from an unclean shutdown. Uploading starts right away if par2 files were already generated.  
All NZB files in the out directory are guaranteed to be without errors.

## About x-cord/Nyuu fork
This fork was made to allow for better obfuscation without compromising on NZB metadata quality, and spoofing of ngPost uploads.  
Notable changes are per-post templating of the From address, randomized filenames while preserving original names in NZB.
