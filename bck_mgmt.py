#!/usr/bin/python3

import yaml
from pathlib import Path
import datetime
import logging
import sys
import shutil
import re
import difflib
#import subprocess

MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK = 1000000 # do not check files bigger than 1MB

#conf_path = "example-config.yaml" # default config path

total_size = 0
total_files = 0
total_files_deleted = 0

report_string = ""
summary_crit_str = ""
summary_warn_str = ""
perfdata_array = []

warn_flag = False
crit_flag = False

usage = """usage: {} -c <config-file> 
See example config for more information.""".format(sys.argv[0])


def humanize_size(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


# Parse arguments:
for arg_num, arg in enumerate(sys.argv[1:], start=1):
    if arg == "-h" or arg == "--help":
        print(usage)
        sys.exit(0)
    elif (arg == "-c" or arg == "--conf") and arg_num < len(sys.argv[1:]):
        conf_path = sys.argv[arg_num+1]

if not conf_path or not Path(conf_path).is_file():
    print(usage)
    sys.exit(3)

# Parse config file:
with open(conf_path, 'r') as stream:
    parsed_config = (yaml.safe_load(stream))

log_cfg = parsed_config['logging']
backup_repo = parsed_config['backup_repository']


logging.basicConfig(filename=log_cfg['file'] if 'file' in  log_cfg.keys() else None, level=log_cfg['level'].upper(), format='%(asctime)s %(levelname)s: %(message)s')

logging.debug("Parsed Config: \n{}".format(parsed_config))


for repo in backup_repo:

    current_dir = Path(repo['directory'])
    subdirs = []

    dir_files = 0
    dir_size = 0
    files_deleted = 0
    newest_file_age = 0
    compliance_violations = 0

    warn_str = ""
    crit_str = ""

    if not current_dir.is_dir():
        crit_str += "Directory '{}' not found. ".format(current_dir)
        logging.error(crit_str)
    else:
        matching_files = current_dir.glob(repo['pattern'])
        sorted_file_list = sorted(((file.stat().st_mtime, file, file.stat().st_size) for file in matching_files if file.is_file()), reverse=True)
        logging.debug("Found {} matching backup files in Directory '{}'. ".format(len(sorted_file_list), current_dir))

    if 'weekly' in repo.keys():
        weekly_path = Path(repo['weekly']['directory'])
        if not weekly_path.is_dir():
            log = "Weekly directory '{}' does not exist. Please create the directory. ".format(weekly_path)
            logging.error(log)
            crit_str += log
        else:
            weeks_in_weekly = list(datetime.date.fromtimestamp(f.stat().st_mtime).isocalendar()[1] for f in weekly_path.glob(repo['pattern']))
            subdirs.append('weekly')

    if 'monthly' in repo.keys():
        monthly_path = Path(repo['monthly']['directory'])
        if not monthly_path.is_dir():
            log = "Monthly directory '{}' does not exist. Please create the directory. ".format(monthly_path)
            logging.error(log)
            crit_str += log
        else:
            months_in_monthly = list(datetime.date.fromtimestamp(f.stat().st_mtime).month for f in monthly_path.glob(repo['pattern']))
            subdirs.append('monthly')

    if 'yearly' in repo.keys():
        yearly_path = Path(repo['yearly']['directory'])
        if not weekly_path.is_dir():
            log = "Yearly directory '{}' does not exist. Please create the directory. ".format(yearly_path)
            logging.error(log)
            crit_str += log
        else:
            years_in_yearly = list(datetime.date.fromtimestamp(f.stat().st_mtime).year for f in yearly_path.glob(repo['pattern']))
            subdirs.append('yearly')

    if crit_str:
        report_string += "\n[CRITICAL] " + crit_str
        summary_crit_str += crit_str
        crit_flag = True
        continue

    if len(sorted_file_list) == 0:
        log = "Directory '{}' does not contain any file matching the pattern '{}'. ".format(current_dir, repo['pattern'])
        logging.warning(log)
        warn_str += log
        #continue

    for file_num, file in enumerate(sorted_file_list):

        current_file = file[1]
        current_file_mtime = datetime.datetime.fromtimestamp(file[0])
        current_file_size = file[2]
        current_file_week = current_file_mtime.isocalendar()[1]
        current_file_month = current_file_mtime.month
        current_file_year = current_file_mtime.year

        # check age and file size of the newest file in the directory:
        if file_num == 0:
            newest_file = current_file
            newest_file_mtime = current_file_mtime
            newest_file_age = datetime.datetime.now() - newest_file_mtime
            newest_file_content = None
            
            logging.debug("'{}' is the newest file in the directory. ".format(newest_file))

            if 'warn_age' in repo.keys() and newest_file_age > datetime.timedelta(days = repo['warn_age']):
                log = "Newest file '{}' is older than defined warn_age (Age: {}, warn_age: {} day{}). ".format(
                    current_file, newest_file_age.days, repo['warn_age'], "" if repo['warn_age'] == 1 else "s"
                )
                logging.warning(log)
                warn_str += log

            if 'warn_bytes' in repo.keys() and current_file_size < repo['warn_bytes']:
                log = "Newest file '{}' is smaller than defined warn_bytes (Size: {}, warn_bytes: {} bytes). ".format(
                    current_file, humanize_size(current_file_size), repo['warn_bytes']
                )
                logging.warning(log)
                warn_str += log

            # get file_content if we need it for compliance_checking or comparing:
            if 'compliance_check' in repo.keys() or ('compare_with_previous' in repo.keys() and repo['compare_with_previous']):
                try:
                    if current_file_size > MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK:
                        raise ValueError("File exceeds MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK")
                    with open(current_file, 'r') as f:
                        newest_file_content = f.read()
                except (ValueError, UnicodeDecodeError) as err:
                    warn_str += "Content of '{}' can't be loaded for compliance check or comparison. See logfile for more details. ".format(current_file)
                    logging.error("Content of '{}' can't be loaded: {}. Skipping compliance check and comparison for this file. Note: Compliance checks and comparisons only work for text files! ".format(current_file, err))
            
            # check newest file for compliance:    
            if 'compliance_check' in repo.keys() and newest_file_content is not None:
                for check in repo['compliance_check']:
                    match = re.search(check['regex'], newest_file_content, re.MULTILINE)
                    must_not_match = True if 'must_not_match' in check.keys() and check['must_not_match'] else False
                    if (match and must_not_match) or (not match and not must_not_match):
                        # compliance violation:
                        compliance_violations += 1
                        if 'violation_message' in check.keys():
                            try: 
                                log = "Compliance violation in file '{}': {} ".format(current_file, match.expand(check['violation_message']) if match else check['violation_message'])
                            except re.error as err:
                                log = "Error: Cannot expand violation_message '{}': {}. ".format(check['violation_message'], err)
                        else:
                            log = "Compliance violation in file '{}': Does {}match regex '{}'. ".format(current_file, "" if match else "not ", check['regex'])
                        logging.critical(log)
                        crit_str += log
                    else:
                        # compliant
                        logging.debug("Newest file '{}' is compliant with regex '{}'. ".format(current_file, check['regex']))

        # compare previous file with newest file:
        if file_num == 1 and 'compare_with_previous' in repo.keys() and repo['compare_with_previous'] and newest_file_content is not None and current_file_size <= MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK:
            with open(current_file, 'r') as f:
                previous_file_content = f.read()
            if previous_file_content == newest_file_content:
                logging.info("Newest file '{}' equals previous file '{}'. ".format(newest_file, current_file))
            else:
                log = "Newest file '{}' has changed compared to previous file '{}'. ".format(newest_file, current_file)
                logging.warning(log)
                warn_str += log

                diff = difflib.unified_diff(
                    previous_file_content.splitlines(keepends=False), 
                    newest_file_content.splitlines(keepends=False), 
                    fromfile=current_file.name, 
                    tofile=newest_file.name, 
                    fromfiledate=current_file_mtime.isoformat(), 
                    tofiledate=newest_file_mtime.isoformat(), 
                    lineterm='',
                    n = 2) # number of lines shown before and after differences
                logging.info('Differences:\n'+'\n'.join(diff))

        # clean up old files:
        if 'keep' in repo.keys() and file_num >= int(repo['keep']):
            # move into subdirectories:
            destination = None

            if 'rename_moved_files' in repo.keys():
                filename = datetime.datetime.now().strftime(repo['rename_moved_files'].format(current_file.name))
                #logging.debug("File '{}' will be renamed to '{}'. ".format(current_file, filename))
            else:
                filename = current_file.name

            if 'weekly' in repo.keys() and weekly_path.is_dir() and not current_file_week in weeks_in_weekly:
                destination = weekly_path / Path(filename)
                weeks_in_weekly.append(current_file_week)
            elif 'monthly' in repo.keys() and monthly_path.is_dir() and not current_file_month in months_in_monthly:
                destination = monthly_path / Path(filename)
                months_in_monthly.append(current_file_month)
            elif 'yearly' in repo.keys() and yearly_path.is_dir() and not current_file_year in years_in_yearly:
                destination = yearly_path / Path(filename)
                years_in_yearly.append(current_file_year)
            elif 'move_old_to' in repo.keys() and Path(repo['move_old_to']).is_dir():
                destination = Path(repo['move_old_to']) / Path(filename)

            if destination is not None:
                if not destination.exists():
                    logging.info("Moving {} to {}. ".format(current_file, destination))
                    current_file = shutil.move(current_file, destination)
                else:
                    logging.error("Destination file already exists. ")
            # delete file:
            elif 'delete_old' in repo.keys() and repo['delete_old']:
                logging.info("Deleting {}. ".format(current_file))
                current_file.unlink()
                files_deleted += 1
            else:
                logging.info("{} would have been deleted, but 'delete_old' is not enabled. ".format(current_file))
                dir_size+=current_file_size
                dir_files+=1

        else:
            dir_size+=current_file_size
            dir_files+=1


    # clean up subdirectories:
    for i in subdirs:
        subdir = Path(repo[i]['directory'])
        keep = int(repo[i]['keep'])

        matching_files = subdir.glob(repo['pattern'])
        sorted_file_list = sorted(((file.stat().st_mtime, file, file.stat().st_size) for file in matching_files if file.is_file()), reverse=True)
        for file_num, file in enumerate(sorted_file_list):
            if file_num < keep:
                dir_size+=file[2]
                dir_files+=1
            elif 'move_old_to' in repo.keys() and Path(repo['move_old_to']).is_dir():
                destination = Path(repo['move_old_to']) / Path(file[1].name)
                if not destination.exists():
                    logging.info("Moving {} to {}. ".format(file[1], destination))
                    shutil.move(file[1], destination)
                else:
                    logging.error("Destination file already exists. ")
            elif 'delete_old' in repo.keys() and repo['delete_old']:
                logging.info("Deleting {}. ".format(file[1]))
                file[1].unlink()
                files_deleted += 1
            else:
                logging.info("{} would have been deleted, but 'delete_old' is not enabled. ".format(file[1]))
                dir_size+=file[2]
                dir_files+=1


    # Reporting + perfdata:
    if crit_str:
        crit_flag = True
        report_string += "\n[CRITICAL] "
    elif warn_str:
        warn_flag = True
        report_string += "\n[WARNING] "
    else:
        report_string += "\n[OK] "

    if 'alias' in repo.keys():
        alias = repo['alias']
    else:
        alias = str(current_dir)

    report_string += alias + ": " + crit_str + warn_str
    report_string += "Directory contains {} matching file{} with {}. ".format(dir_files, "" if dir_files == 1 else "s", humanize_size(dir_size) )
    if dir_files > 0:
        report_string += "Newest file is {} days old. {} file{} deleted. ".format( newest_file_age.days, files_deleted, "" if files_deleted == 1 else "s")
    if compliance_violations == 0 and 'compliance_check' in repo.keys():
        report_string += "No compliance violations. "

    alias = alias.replace(" ","_")
    perfdata_array.append("{}_files={}".format(alias, dir_files))
    perfdata_array.append("{}_size={}b".format(alias, dir_size))
    if dir_files > 0:
        perfdata_array.append("{}_age={}{}".format(alias, newest_file_age.days, (";" + str(repo['warn_age'])) if 'warn_age' in repo.keys() else ""))
        perfdata_array.append("{}_deleted={}".format(alias, files_deleted))


    total_size+=dir_size
    total_files+=dir_files
    total_files_deleted+=files_deleted

    summary_crit_str += crit_str
    summary_warn_str += warn_str


report_summary = summary_crit_str + summary_warn_str
report_summary += "Total {} matching file{} with {}. {} file{} deleted. ".format(
    total_files, "" if total_files == 1 else "s", humanize_size(total_size), total_files_deleted, "" if total_files_deleted == 1 else "s"
)

report_string = report_summary + report_string

perfdata_array.append("total_files={}".format(total_files))
perfdata_array.append("total_size={}b".format(total_size))
perfdata_array.append("total_deleted={}".format(total_files_deleted))

perfdata_string = ""
for perfdata in perfdata_array:
    perfdata_string += perfdata + " "

if crit_flag: exitcode = 2
elif warn_flag: exitcode = 1
else: exitcode = 0

# report_string now contains all the relevant information in human readable form which can be sent by mail or to a monitoring system.
# perfdata_array contains statistics in an array. perfdata_string contains the same data in a string seperated by spaces.
# for example you can call your own script which processes the data like this:
#subprocess.run(['process_check_result.sh', '-e', str(exitcode), '-o', report_string.replace("\n", "\\n") , '-d', perfdata_string ], check=True )

logging.info(" ===== Execution Report ===== \n{}\n ".format(report_string))
logging.debug(" ========= Perfdata ========= \n{}\n ".format(perfdata_string))


sys.exit(exitcode)
