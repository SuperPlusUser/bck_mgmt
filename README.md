# bck_mgmt.py - A configurable python backup management script

This script allows you to automatically clean up and monitor your backup repositories. It is designed to be run regularly e.g. by a cron job. It works for any backup files as long as they match the configured pattern in the specified YAML config file.

## Features
 - define custom backup retention policy:
   - keep X most recent backup files
   - keep X weekly, monthly and yearly backup files
 - check if newest backup file is to old or to small (which could indicate a transmission problem, for example)
 - compliance checks: check if the newest backup file matches specified regular expressions and define custom violation messages (only for text files)
 - compare newest file with previous file and warn if there are changes (or not)
 - log differences between the 2 most recent files (only for text files)
 - delete newest file if it is equal to previous file (useful for configuration files etc. if you only want to keep a new backup if something changed)
 - log to log file or stdout with configurable log level
 - The script can be modified to send custom reports and statistics via mail or to a monitoring system (see comment at the end of the script)
 
## Usage
```
Usage:
  {} -c <config> [-d] [-h]

Options:
  -c, --conf <config>  specify path to YAML config file. See example config for more information.
  -d, --debug          overwrites log config to DEBUG and STDOUT
  -h, --help           display this help and exit
```

## Requirements
 - Python 3.4 or newer
 - Tested on Windows and Linux (Ubuntu)

## How does it work?
You need to define your backup directories in a YAML config file. The supplied sample config shows how to do that. For each directory the script will create a sorted list of all backup files matching the configured pattern. The files are sorted by modification time. If multiple files have the same modification time, they are sorted alphabetically. The script will than check the age and size of the most recent file. If it is a text file, compliance checks will also be performed according to the defined regular expressions. 

If there are more matching files in the directory than the defined "keep" value, the script will then move the excess files to the configured yearly | monthly | weekly directories. If they allready include a file of the same year | month | week, the excess files will be deleted instead (if delete_old = true). 
The script will not create a copy of a file. For example, it will not move the same file to the monthly and weekly directory, but only to the monthly. The next one from the same month will then be moved to the weekly directory.
 
Weekly, monthly and yearly directories are optional. If the backup files in the base directory are created weekly or less often, it does not make sense to define a weekly directory.
 
All configured directory paths have to exist. The script itself will not create or delete any directories.

Make sure you test the script with non-critical files first. You can also set "delete_old" to false for testing. In this case, the script only logs which files would have been deleted.