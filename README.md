# bck_mgmt.py - a simple and configurable python backup management script

This script allows you to automatically clean up and monitor your backup repositories. It is designed to be run regularly e.g. by a cron job. It works for any backup files as long as they match the configured pattern in the specified  yaml config file.

## Features
 - keep X most recent backup files
 - keep weekly, monthly and yearly backup files
 - check if newest backup file is to old or to small
 - The script can be modified to send custom reports and statistics via mail or to a monitoring system.
 
## Usage
`bck_mgmt.py -c <config.yaml>`

## Requirements
Python 3.4 or newer
should work with Windows and Linux, but only tested on Linux (Ubuntu)

## How does it work?
The script will create a sorted list of all files in the configured directory matching the configured pattern. The files are sorted by modification time. If multiple files have the same modification time, they are sorted alphabetically. The script will than check the age and size of the first (= newest) file. If there are more matching files in the directory than the defined "keep" value, the script will than check if there are already files of the same week|month|year in  the defined weekly|monthly|yearly directories. If no, the excess file will be moved there. If yes, the file will be deleted (if delete_old = true). The script will only move a file once. For example it will not move the same file to the weekly and monthly directory, but only to the weekly (and the next one to the monthly directory, if it is from the same week).
 
Weekly, monthly and yearly directories are optional. If the backup files in the base directory are created weekly or less frequently, it does not make sense to define a weekly directory.
 
All configured directory paths have to exist. The script itself will not create or delete any directories.

Take a look at the supplied example config for more details.