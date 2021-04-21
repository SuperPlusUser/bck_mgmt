# bck_mgmt.py - a simple and configurable python backup management script

This script allows you to automatically clean up and monitor your backup repositories. It is designed to be run regularly e.g. by a cron job. It works for any backup files as long as they match the configured pattern in the specified YAML config file.

## Features
 - keep only X most recent backup files
 - keep weekly, monthly and yearly backup files
 - check if newest backup file is to old or to small (not complete)
 - The script can be modified to send custom reports and statistics via mail or to a monitoring system.
 
## Usage
`bck_mgmt.py -c <path to config.yaml>`

## Requirements
 - Python 3.4 or newer
 - Should work with Windows and Linux, but only tested on Linux (Ubuntu)

## How does it work?
You need to define your backup directories in a YAML config file. The supplied sample config shows how to do that. For each directory the script will create a sorted list of all backup files matching the configured pattern. The files are sorted by modification time. If multiple files have the same modification time, they are sorted alphabetically. The script will than check the age and size of the first (= newest) file. It will warn you according to the configured "warn_age" and "warn_bytes" values.

If there are more matching files in the directory than the defined "keep" value, the script will then move the excess files to the configured weekly | monthly | yearly directories. If they allready include a file of the same week | month | year, the excess files will be deleted instead (only if delete_old = true). 
The script will not create a copy of a file. For example, it will not move the same file to the weekly and monthly directory, but only to the weekly. The next one from the same week will then be moved to the monthly directory.
 
Weekly, monthly and yearly directories are optional. If the backup files in the base directory are created weekly or less often, it does not make sense to define a weekly directory.
 
All configured directory paths have to exist. The script itself will not create or delete any directories.
