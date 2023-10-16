# bck_mgmt.py - A configurable python backup management script

This script allows you to automatically clean up and monitor your backup repositories. It is designed to be run regularly, e.g. by a cron job. It works for any backup files as long as they match the configured pattern in the specified YAML config file.

## Features

* define custom backup retention policy: 
  * keep X most recent backup files
  * keep X weekly, monthly and yearly backup files
* check if newest backup file is too old or too small (which could indicate a transmission problem, for example)
* compliance checks: check if the newest backup file matches specified regular expressions and define custom violation messages (only for text files)
* compare newest file with previous file and warn if there are changes (or not)
* log differences between the 2 most recent files (only for text files)
* delete newest file if it is equal to previous file (useful for configuration files etc. if you only want to keep a new backup if something changed)
* log to log file or stdout with configurable log level
* execute custom (pull-)command to generate backup files
* define custom commands to send reports and statistics e.g. via mail or to a monitoring system

## Usage

```
Usage:
  bck_mgmt.py -c <config> [-d] [-h]

Options:
  -c, --conf <config>  specify path to YAML config file. See example config for more information.
  -d, --debug          overwrites log config to DEBUG and STDOUT
  -h, --help           display this help and exit
  -v, --version        display version and exit
```

## Requirements

* Python 3.6 or newer
* Uses only libraries from Python Standard Library, except PyYAML, which has to be installed using `pip install PyYAML`
* Should work on Windows and most Linux Distros (Tested on Windows 11, Ubuntu 22.04 and Debian 11)

## How does it work?

You need to define your backup directories in a YAML config file. The supplied sample config shows how to do that. For each directory, the script will create a sorted list of all backup files matching the configured pattern. The files are sorted by modification time. If multiple files have the same modification time, they are sorted alphabetically. The script will then check the age and size of the most recent file. If it is a text file, compliance checks will also be performed according to the defined regular expressions.

If there are more matching files in the directory than the defined "keep" value, the script will then move the excess files to the configured yearly | monthly | weekly directories. If they already include a file of the same year | month | week, the excess files will be deleted instead (if delete_old = true).
The script will not create a copy of a file. For example, it will not move the same file to the monthly and weekly directory, but only to the monthly. The next one from the same month will then be moved to the weekly directory.

Weekly, monthly and yearly directories are optional. If the backup files in the base directory are created weekly or less often, it does not make sense to define a weekly directory.

All configured directory paths have to exist. The script itself will not create or delete any directories.

Make sure you test the script with non-critical files first. You can also set "delete_old" to false for testing. In this case, the script only logs which files would have been deleted.

## Configuration

### defaults:

This section allows you to define default values that apply to all directories defined under `backup_repository`. All options from directory definitions are allowed (see below). Options can be overwritten for individual directories. Dictionaries (like `weekly:`) and lists (like `compliance_check:`) will be combined to one dict / list including all items from default section and individual directory config.

### backup_repository:

Here you define a list of your backup base directories. For each base directory you can set the following options:

- **directory** *(required, path)*: Base directory path of the backup repository. Should be an absolute path.
- **alias** *(optional, string)*: An optional alias for the repository, which will be used in reports and logs.
- **pattern** *(required, string)*: The pattern of backup files to process. Use "*" as wildcard character and put the entire expression into quotation marks. "**" can be used to also search files in subdirectories recursively (Use with caution!).
- **keep** *(optional, int)*: Number of recent backup files to keep in the base directory.
- **warn_age** *(optional, int)*: Number of days to issue a warning if the newest file is older.
- **warn_bytes** *(optional, int)*: Number of bytes below which a warning is issued if the newest file is smaller.
- **delete_old** *(required, bool)*: Whether old files should be deleted. If set to false or omitted, the script will only log the files, which would have been deleted (useful for tests).
- **move_old_to** *(optional, path)*: The optional directory to move old files to instead of deleting them. Overwrites 'delete_old'.
- **rename_moved_files** *(optional, string)*: The optional naming convention for moved files. '{}' will be replaced by the original filename. Make sure the given 'pattern' still matches after renaming! % format codes can be used to add date and time. `%Y-%m-%d` will be replaced by the year, month and day the file was moved. See https://strftime.org/ for available format codes. 
- **pull** *(optional)*: Pull backups using custom command
    - **command** *(required, string)*: The (shell-)command to execute the pull operation. % format codes can be used to add date and time. See https://strftime.org/ for available format codes.
    - **shell** *(optional, bool)*: Whether to execute the command in the shell.
    - **timeout** *(optional, int)*: The timeout for the pull operation in seconds.
- **weekly** *(optional)*:
    - **directory** *(required, path)*: Directory for keeping weekly backups (must be already existing).
    - **keep** *(required, int)*: Number of weekly backups to keep.
- **monthly** *(optional)*:
    - **directory** *(required, path)*: Directory for keeping monthly backups (must be already existing).
    - **keep** *(required, int)*: Number of monthly backups to keep.
- **yearly** *(optional)*:
    - **directory** *(required, path)*: Directory for keeping yearly backups (must be already existing).
    - **keep** *(required, int)*: Number of yearly backups to keep.
- **compliance_check** *(optional, list)*: Check if content of newest backup file matches the given regular expressions. Only works for text files!
    - **regex** *(required, string)*: Regular expression for content check. Put 'single quotes' around regex and violation message! All Python regular expressions should work. See https://www.rexegg.com/regex-quickstart.html for example.
    - **violation_message** *(optional, string)*: Violation message for non-matching content.
    - **must_not_match** *(optional, bool)*: If true: raise a violation if the regex matches.
- **compare_with_previous** *(optional)*: Compare newest file with previous file. For this to work properly, the script should be run at the same interval at which the backup files are generated.
    - **warn_if_changed** *(optional, bool)*: Warn if the newest file changed compared to the previous one.
    - **warn_if_equal** *(optional, bool)*: Warn if the newest file equals the previous one.
    - **log_diff** *(optional, bool)*: Log the differences between the two most recent files at INFO level. Only works for text files smaller than 1MB (like config files etc.). Log will become large if there are many changes!
    - **delete_if_equal** *(optional, bool)*: Only keep the newest file if it differs from the previous one, otherwise delete it.
    - **warn_age_limit** *(optional, int)*: Age limit for warnings about changes. No warning is issued, if newest file is older than the defined age in days.
    - **ignore_regex** *(optional, string)*: Regex to ignore parts of the file. No warning is issued for changes in ignored parts. Only works for text files smaller than 1MB.
    - **delete_if_ignored** *(optional, bool)*: Delete newest file if only ignored parts changed. Has no effect if `delete_if_equal` is not set to true.

### logging:

- **level** *(required, string)*: The log level (options: debug, info, warning, error, critical).
- **file** *(optional, path)*: The path to the log file. If omitted, log will go to stdout.

### reporting:

- **command** *(required, string)*: The command to execute the reporting process.\
The following variables will be substituted at runtime:\
`{exitcode}` (integer): 0 = ok, 1 = warning, 2 = critical\
`{exitstatus}` (string): "OK", "WARNING" or "CRITICAL"\
`{report}` (string): multiline execution report and summary of all repositories\
`{perfdata}` (string): performance data in Nagios compatible format\
% format codes can be used to add date and time. See https://strftime.org/ for available format codes.
- **shell** *(optional, bool)*: Whether to execute the command in the shell.

### Minimal Example

```
defaults:
  warn_age: 7
  delete_old: true

backup_repository:

  - directory: /data/backups/test_repo1
    alias: Test-Repo 1
    pattern: "*.bck"
    keep: 7
    monthly:
        directory: monthly
        keep: 6

  - directory: /data/backups/test_repo2
    alias: Test-Repo 2
    pattern: "*.bck"
    keep: 10

logging:
    level: warning

reporting:
    command: 'echo {report} | mail -s "Backup Management Script exited with status {exitstatus} at %d.%m.%Y %H:%M:%S" your-mail@example.com'
    shell: True

```
for a more complex example see [example-config.yaml](example-config.yaml)