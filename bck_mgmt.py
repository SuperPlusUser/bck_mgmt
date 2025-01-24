#!/usr/bin/python3

import yaml # requires pyyaml (pip install pyyaml)
from pathlib import Path
import datetime
import logging
import sys
import shutil
import re
import difflib
import filecmp
import subprocess
import shlex

VERSION = "1.6 (24.01.2025)"
MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK = 1048576 # do not check files bigger than 1MB (a quite conservative limit to avoid high mem usage or to long log output)
DEBUG = False

conf_path = None # default config path can be set here

usage = """Usage:
  {} -c <config> [-d] [-h]

Options:
  -c, --conf <config>  specify path to YAML config file. See example config for more information.
  -d, --debug          overwrites log config to DEBUG and STDOUT
  -h, --help           display this help and exit
  -v, --version        display version and exit""".format(sys.argv[0])


def humanize_size(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)

def load_file_content(file, file_size):
    file_content = None
    logging.debug("Loading content of file '{}' for comparison or compliance checking. ".format(file))
    try:
        if file_size > MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK:
            raise ValueError("File exceeds MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK")
        with open(file, 'r') as f:
            file_content = f.read()
    except (ValueError, UnicodeDecodeError) as err:
        logging.error("Content of '{}' can't be loaded: {}. Skipping compliance check and diff log for this file. Note: Compliance check and diff log only work for text files smaller than {}! ".format(file, err, humanize_size(MAX_FILE_SIZE_FOR_COMPLIANCE_CHECK)))
    return file_content

def main(config_file):
    total_size = 0
    total_files = 0
    total_files_deleted = 0

    report_string = ""
    summary_crit_str = ""
    summary_warn_str = ""
    perfdata_array = []

    warn_flag = False
    crit_flag = False

    # Parse config file:
    with open(config_file, 'r') as stream:
        parsed_config = yaml.safe_load(stream)

    log_cfg = parsed_config['logging']
    backup_repo = parsed_config['backup_repository']

    # Logging config:
    if DEBUG:
        logging.basicConfig(filename=None, level="DEBUG", format='%(asctime)s %(levelname)s: %(message)s')
    else:
        logging.basicConfig(filename=log_cfg['file'] if 'file' in log_cfg.keys() else None, level=log_cfg['level'].upper(), format='%(asctime)s %(levelname)s: %(message)s')

    logging.debug("Parsed Config: \n{}".format(parsed_config))


    for repo in backup_repo:

        current_dir = Path(repo['directory'])
        subdirs = []

        dir_files = 0
        dir_size = 0
        files_deleted = 0
        newest_file_deleted = 0
        compliance_violations = 0
        newest_file = None
        newest_file_content = None
        newest_file_size = 0
        newest_file_mtime = datetime.datetime.fromtimestamp(0)
        newest_file_age = datetime.datetime.now() - newest_file_mtime
        yearly_path = monthly_path = weekly_path = move_old_path = None
        years_in_yearly	 = months_in_monthly = weeks_in_weekly = []

        warn_str = ""
        crit_str = ""
        
        # List of files in the directory. Each file is represented by a tuple containing the modification time, the file object and the file size
        sorted_file_list: list[tuple[float, Path, int]] = []

        if 'alias' in repo.keys():
            alias = repo['alias']
        else:
            alias = str(current_dir)

        # load defaults for config entries not defined for current dir:
        if 'defaults' in parsed_config.keys() and type(parsed_config['defaults']) is dict:
            for key in parsed_config['defaults'].keys():
                if not key in repo.keys():
                    repo[key] =  parsed_config['defaults'][key]
                # merge dicts (like 'weekly:' etc.): 
                elif type(repo[key]) is dict and type(parsed_config['defaults'][key]) is dict:
                    repo[key] = {**parsed_config['defaults'][key], **repo[key]}
                # combine lists (only used for compliance checks at the moment):
                # if the following two lines are commented out, lists defined for one directory will overwrite lists defined in defaults section:
                elif type(repo[key]) is list and type(parsed_config['defaults'][key]) is list:
                    repo[key] = parsed_config['defaults'][key] + repo[key]
            logging.debug("{}: Resulting merged config:\n{}".format(alias, repo))

        if not current_dir.is_dir():
            crit_str += "Directory '{}' not found. ".format(current_dir)
            logging.error(alias + ": " + crit_str)
        else:
            # pull backup if pull command is given:
            if 'pull' in repo.keys() and 'command' in repo['pull'].keys():
                command = datetime.datetime.now().strftime(repo['pull']['command'])
                logging.debug("{}: Executing pull command: {}".format(alias, command))
                if 'shell' in repo['pull'].keys() and repo['pull']['shell']:
                    shell = True
                else:
                    shell = False
                    command = shlex.split(command)
                try:
                    command_output = subprocess.run(command,
                        shell = shell, 
                        timeout = repo['pull']['timeout'] if 'timeout' in repo['pull'].keys() else None,
                        capture_output = True,
                        cwd = current_dir)
                    if command_output.stderr:
                        logging.error("{}: An error occurred during execution of pull command: {}".format(alias, command_output.stderr.decode(errors='ignore')))
                    if command_output.stdout:
                        logging.info("{}: Output of pull command: {}".format(alias, command_output.stdout.decode(errors='ignore')))
                except subprocess.TimeoutExpired:
                    logging.error("{}: Timeout for pull command expired.".format(alias))

            matching_files = current_dir.glob(repo['pattern'])
            sorted_file_list = sorted(((file.stat().st_mtime, file, file.stat().st_size) for file in matching_files if file.is_file()), reverse=False)
            logging.debug("{}: Found {} matching backup files in Directory '{}'. ".format(alias, len(sorted_file_list), current_dir))

        if 'weekly' in repo.keys() and 'directory' in repo['weekly'].keys():
            weekly_path = current_dir / Path(repo['weekly']['directory']) # if weekly path is absolute already, current_dir will be ignored
            if not weekly_path.is_dir():
                log = "Weekly directory '{}' does not exist. Please create the directory. ".format(weekly_path)
                logging.error(alias + ": " + log)
                crit_str += log
                weekly_path = None
            else:
                weeks_in_weekly = list(datetime.date.fromtimestamp(f.stat().st_mtime).strftime("%G-%V") for f in weekly_path.glob(repo['pattern']))
                logging.debug("{}: Found weekly directory '{}' with files from the following weeks: {}. ".format(alias, weekly_path, weeks_in_weekly))
                subdirs.append('weekly')

        if 'monthly' in repo.keys() and 'directory' in repo['monthly'].keys():
            monthly_path = current_dir / Path(repo['monthly']['directory'])
            if not monthly_path.is_dir():
                log = "Monthly directory '{}' does not exist. Please create the directory. ".format(monthly_path)
                logging.error(alias + ": " + log)
                crit_str += log
                monthly_path = None
            else:
                months_in_monthly = list(datetime.date.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m") for f in monthly_path.glob(repo['pattern']))
                logging.debug("{}: Found monthly directory '{}' with files from the following months: {}. ".format(alias, monthly_path, months_in_monthly))
                subdirs.append('monthly')

        if 'yearly' in repo.keys() and 'directory' in repo['yearly'].keys():
            yearly_path = current_dir / Path(repo['yearly']['directory'])
            if not yearly_path.is_dir():
                log = "Yearly directory '{}' does not exist. Please create the directory. ".format(yearly_path)
                logging.error(alias + ": " + log)
                crit_str += log
                yearly_path = None
            else:
                years_in_yearly = list(datetime.date.fromtimestamp(f.stat().st_mtime).strftime("%Y") for f in yearly_path.glob(repo['pattern']))
                logging.debug("{}: Found yearly directory '{}' with files from the following years: {}. ".format(alias, yearly_path, years_in_yearly))
                subdirs.append('yearly')

        if 'move_old_to' in repo.keys():
            move_old_path = current_dir / Path(repo['move_old_to'])
            if not move_old_path.is_dir():
                log = "'move_old_to' directory '{}' does not exist. Please create the directory. ".format(move_old_path)
                logging.error(alias + ": " + log)
                crit_str += log
                move_old_path = None

        if crit_str:
            report_string += "\n[CRITICAL] " + crit_str
            summary_crit_str += crit_str
            crit_flag = True
            continue

        if len(sorted_file_list) == 0:
            log = "Directory '{}' does not contain any file matching the pattern '{}'. ".format(current_dir, repo['pattern'])
            logging.warning(alias + ": " + log)
            warn_str += log
            #continue
        else: 
            # check newest file in the directory:
            newest_file = sorted_file_list[-1][1]
            newest_file_size = sorted_file_list[-1][2]
            newest_file_mtime = datetime.datetime.fromtimestamp(sorted_file_list[-1][0])
            newest_file_age = datetime.datetime.now() - newest_file_mtime

            logging.debug("{}: '{}' is the newest file in the directory. ".format(alias, newest_file))

            # check age of newest file:
            if 'warn_age' in repo.keys() and newest_file_age > datetime.timedelta(days = repo['warn_age']):
                log = "Newest file '{}' is older than defined warn_age (Age: {}, warn_age: {} day{}). ".format(
                    newest_file.name, newest_file_age.days, repo['warn_age'], "" if repo['warn_age'] == 1 else "s"
                )
                logging.warning(alias + ": " + log)
                warn_str += log

            # check size of newest file:
            if 'warn_bytes' in repo.keys() and newest_file_size < repo['warn_bytes']:
                log = "Newest file '{}' is smaller than defined warn_bytes (Size: {}, warn_bytes: {} bytes). ".format(
                    newest_file.name, humanize_size(newest_file_size), repo['warn_bytes']
                )
                logging.warning(alias + ": " + log)
                warn_str += log

            # check newest file for compliance:
            if 'compliance_check' in repo.keys():
                newest_file_content = load_file_content(newest_file, newest_file_size)
                if newest_file_content is None:
                    warn_str += "Content of '{}' can't be loaded for compliance checking. See log file for more details. ".format(newest_file.name)
                else:
                    for check in repo['compliance_check']:
                        match = re.search(check['regex'], newest_file_content, flags=re.MULTILINE)
                        must_not_match = True if 'must_not_match' in check.keys() and check['must_not_match'] else False
                        if (match and must_not_match) or (not match and not must_not_match):
                            # compliance violation:
                            compliance_violations += 1
                            if 'violation_message' in check.keys():
                                try: 
                                    log = "Compliance violation in file '{}': {} ".format(newest_file.name, match.expand(check['violation_message']) if match else check['violation_message'])
                                except re.error as err:
                                    log = "Error: Cannot expand violation_message '{}': {}. ".format(check['violation_message'], err)
                            else:
                                log = "Compliance violation in file '{}': Does {}match regex '{}'. ".format(newest_file.name, "" if match else "not ", check['regex'])
                            logging.critical(alias + ": " + log)
                            crit_str += log
                        else:
                            # compliant
                            logging.debug("{}: Newest file '{}' is compliant with regex '{}'. ".format(alias, newest_file.name, check['regex']))

        # compare newest file with previous file:
        if 'compare_with_previous' in repo.keys() and newest_file and len(sorted_file_list) >= 2:
            comp_cfg = repo['compare_with_previous']

            previous_file = sorted_file_list[-2][1]
            previous_file_size = sorted_file_list[-2][2]
            previous_file_mtime = datetime.datetime.fromtimestamp(sorted_file_list[-2][0])
            previous_file_content = None

            ignore_changes = False

            if filecmp.cmp(previous_file, newest_file, shallow=False):
                # files are the same:
                file_changed = False
                if 'warn_age_limit' in comp_cfg.keys() and newest_file_age > datetime.timedelta(days = comp_cfg['warn_age_limit']):
                    logging.debug("{}: Newest file '{}' equals previous file and is older than defined 'warn_age_limit' for comparison. ".format(alias, newest_file.name))
                else:
                    log = "Content of newest file '{}' equals content of previous file '{}'. ".format(newest_file.name, previous_file.name)
                    if 'warn_if_equal' in comp_cfg.keys() and comp_cfg['warn_if_equal']:
                        logging.warning(alias + ": " + log)
                        warn_str += log
                    else:
                        logging.info(alias + ": " + log)

            else: # newest file is different than previous:
                file_changed = True
                if 'warn_age_limit' in comp_cfg.keys() and newest_file_age > datetime.timedelta(days = comp_cfg['warn_age_limit']):
                    logging.debug("{}: Newest file '{}' has changed compared to previous file and is older than defined 'warn_age_limit' for comparison. ".format(alias, newest_file.name))
                else:
                    log = "Newest file '{}' has changed compared to previous file '{}'. ".format(newest_file.name, previous_file.name)
                    
                    # check if changes are ignored by 'ignore_regex':
                    if 'ignore_regex' in comp_cfg.keys():
                        if newest_file_content is None:
                            newest_file_content = load_file_content(newest_file, newest_file_size)
                        if newest_file_content is not None and previous_file_content is None:
                            previous_file_content = load_file_content(previous_file, previous_file_size)
                        
                        if newest_file_content is not None and previous_file_content is not None:
                            newest_file_content_reduced = re.sub(comp_cfg['ignore_regex'], '[IGNORED]', newest_file_content, flags=re.MULTILINE)
                            previous_file_content_reduced = re.sub(comp_cfg['ignore_regex'], '[IGNORED]', previous_file_content, flags=re.MULTILINE)
                            logging.debug("{}: previous file content after applying 'ignore_regex':\n{}\nnewest file content after applying 'ignore_regex':\n{}".format(
                                alias, previous_file_content_reduced, newest_file_content_reduced))
                            if previous_file_content_reduced == newest_file_content_reduced:
                                ignore_changes = True
                        else:
                            log_err = "'ignore_regex' for comparison can't be applied. "
                            warn_str += (log_err + "See log file for details. ")
                            logging.error(alias + ": " + log_err)
                    
                    if 'warn_if_changed' in comp_cfg.keys() and comp_cfg['warn_if_changed'] and not ignore_changes:
                        logging.warning(alias + ": " + log)
                        warn_str += log
                    elif ignore_changes:
                        logging.info(alias + ": " + log + "All changes are ignored because of 'ignore_regex'. ")
                    else:
                        logging.info(alias + ": " + log)

                    # log diff:
                    if 'log_diff' in comp_cfg and comp_cfg['log_diff'] and logging.getLogger().level <= 20 and not ignore_changes:
                        if newest_file_content is None:
                            newest_file_content = load_file_content(newest_file, newest_file_size)
                        if newest_file_content is not None and previous_file_content is None:
                            previous_file_content = load_file_content(previous_file, previous_file_size)
                        
                        if newest_file_content is not None and previous_file_content is not None:
                            diff = difflib.unified_diff(
                                previous_file_content.splitlines(keepends=False),
                                newest_file_content.splitlines(keepends=False),
                                fromfile=previous_file.name,
                                tofile=newest_file.name,
                                fromfiledate=previous_file_mtime.isoformat(),
                                tofiledate=newest_file_mtime.isoformat(),
                                lineterm='',
                                n = 2) # number of lines shown before and after differences
                            logging.info('Differences:\n'+'\n'.join(diff))
                        else:
                            log_err = "Differences between '{}' and '{}' cannot be logged. ".format(newest_file.name, previous_file.name)
                            warn_str += (log_err + "See log file for details. ")
                            logging.error(alias + ": " + log_err)

            # delete newest file if delete_if_equal is set and there are no changes or the changes are ignored because of ignore_regex
            if 'delete_if_equal' in comp_cfg.keys() and comp_cfg['delete_if_equal'] and ( not file_changed or (ignore_changes and 'delete_if_ignored' in comp_cfg.keys() and comp_cfg['delete_if_ignored']) ):
                if file_changed:
                    logging.info("{}: Deleting '{}' because all changes are ignored by 'ignore_regex' and 'delete_if_ignored' is set to true. ".format(alias, newest_file.name))
                else:
                    logging.info("{}: Deleting '{}' because it is the same as the previous file. ".format(alias, newest_file.name))
                newest_file.unlink()
                newest_file_deleted += 1
                sorted_file_list.remove(sorted_file_list[-1])


        # clean up old files:
        for file_num, file in enumerate(sorted_file_list):
            current_file = file[1]
            current_file_mtime = datetime.datetime.fromtimestamp(file[0])
            current_file_size = file[2]
            current_file_week = current_file_mtime.strftime("%G-%V")
            current_file_month = current_file_mtime.strftime("%Y-%m")
            current_file_year = current_file_mtime.strftime("%Y")

            if 'keep' in repo.keys() and ( len(sorted_file_list) - file_num ) > int(repo['keep']):
                # move into subdirectories:
                destination = None

                if 'rename_moved_files' in repo.keys():
                    filename = datetime.datetime.now().strftime(repo['rename_moved_files'].format(current_file.name))
                    #logging.debug("File '{}' will be renamed to '{}'. ".format(current_file, filename))
                else:
                    filename = current_file.name

                if yearly_path and not current_file_year in years_in_yearly:
                    destination = yearly_path / Path(filename)
                    years_in_yearly.append(current_file_year)
                elif monthly_path and not current_file_month in months_in_monthly:
                    destination = monthly_path / Path(filename)
                    months_in_monthly.append(current_file_month)
                elif weekly_path and not current_file_week in weeks_in_weekly:
                    destination = weekly_path / Path(filename)
                    weeks_in_weekly.append(current_file_week)
                elif move_old_path:
                    destination = move_old_path / Path(filename)

                if destination is not None:
                    if not destination.exists():
                        logging.info("{}: Moving '{}' to '{}'. ".format(alias, current_file.name, destination))
                        current_file = shutil.move(current_file, destination)
                    else:
                        logging.error("{}: Cannot move '{}' to '{}'. Destination file already exists! ".format(alias, current_file.name, destination))
                # delete file:
                elif 'delete_old' in repo.keys() and repo['delete_old']:
                    logging.info("{}: Deleting '{}'. ".format(alias, current_file.name))
                    current_file.unlink()
                    files_deleted += 1
                else:
                    logging.info("{}: '{}' would have been deleted, but 'delete_old' is not enabled. ".format(alias, current_file.name))
                    dir_size+=current_file_size
                    dir_files+=1

            else:
                dir_size+=current_file_size
                dir_files+=1


        # clean up subdirectories:
        for i in subdirs:
            subdir = current_dir / Path(repo[i]['directory'])
            keep = int(repo[i]['keep'])

            matching_files = subdir.glob(repo['pattern'])
            sorted_file_list = sorted(((file.stat().st_mtime, file, file.stat().st_size) for file in matching_files if file.is_file()), reverse=True)
            logging.debug("{}: Found {} matching backup files in {} subdirectory. ".format(alias, len(sorted_file_list), i))
            for file_num, file in enumerate(sorted_file_list):
                if file_num < keep:
                    dir_size+=file[2]
                    dir_files+=1
                elif 'move_old_to' in repo.keys() and move_old_path:
                    destination = move_old_path / Path(file[1].name)
                    if not destination.exists():
                        logging.info("{}({}): Moving '{}' to '{}'. ".format(alias, i, file[1].name, destination))
                        shutil.move(file[1], destination)
                    else:
                        logging.error("{}({}): Cannot move '{}' to '{}'. Destination file already exists! ".format(alias, i, file[1], destination))
                elif 'delete_old' in repo.keys() and repo['delete_old']:
                    logging.info("{}({}): Deleting '{}'. ".format(alias, i, file[1].name))
                    file[1].unlink()
                    files_deleted += 1
                else:
                    logging.info("{}({}): '{}' would have been deleted, but 'delete_old' is not enabled. ".format(alias, i, file[1].name))
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

        report_string += alias + ": " + crit_str + warn_str
        report_string += "Repository contains {} matching file{} with {}. ".format(dir_files, "" if dir_files == 1 else "s", humanize_size(dir_size) )
        if newest_file:
            if newest_file_deleted:
                report_string += "Newest file was {} day{} old ".format(newest_file_age.days, "" if newest_file_age.days == 1 else "s")
                report_string += "and was deleted, because there were no relevant changes. "
            else:
                report_string += "Newest file is {} day{} old. ".format(newest_file_age.days, "" if newest_file_age.days == 1 else "s")
        report_string += "{} old file{} deleted. ".format(files_deleted, "" if files_deleted == 1 else "s")
        if compliance_violations == 0 and 'compliance_check' in repo.keys():
            report_string += "No compliance violations. "

        alias = alias.replace(" ","_")
        perfdata_array.append("{}_files={}".format(alias, dir_files))
        perfdata_array.append("{}_size={}b".format(alias, dir_size))
        if newest_file:
            perfdata_array.append("{}_age={}{}".format(alias, newest_file_age.days, (";" + str(repo['warn_age'])) if 'warn_age' in repo.keys() else ""))
            perfdata_array.append("{}_deleted={}".format(alias, files_deleted + newest_file_deleted))


        total_size+=dir_size
        total_files+=dir_files
        total_files_deleted+=(files_deleted + newest_file_deleted)

        # comment out the following 2 lines, if you dont't want all critical and warning strings of individual repositories to also be displayed in the report summary (first line of report string)
        summary_crit_str += crit_str
        summary_warn_str += warn_str


    report_summary = summary_crit_str + summary_warn_str
    report_summary += "Total {} matching file{} with {} in {} backup repositor{}. {} file{} deleted. ".format(
        total_files, "" if total_files == 1 else "s", humanize_size(total_size), len(backup_repo), "y" if len(backup_repo) == 1 else "ies",
        total_files_deleted, "" if total_files_deleted == 1 else "s"
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

    exitstatus_string = ["OK","WARNING","CRITICAL"][exitcode]

    # Reporting:

    # report_string now contains all the relevant information in human readable form which can be sent by mail or to a monitoring system.
    # perfdata_array contains statistics in an array. 
    # perfdata_string contains the same data in a string separated by spaces.

    if 'reporting' in parsed_config.keys():
        reporting_config = parsed_config['reporting']
        if 'command' in reporting_config.keys():
            # escape variables:
            escaped_report_string     = shlex.quote(report_string)
            escaped_perfdata_string   = shlex.quote(perfdata_string)
            # replace variables in command:
            command = datetime.datetime.now().strftime(reporting_config['command']).format(
                exitcode   = str(exitcode),
                exitstatus = exitstatus_string,
                report     = escaped_report_string, 
                perfdata   = escaped_perfdata_string)
            if 'shell' in reporting_config.keys() and reporting_config['shell']:
                shell = True
            else:
                shell = False
                command = shlex.split(command)
            logging.debug("Executing reporting command: {}".format(command))
            command_output = subprocess.run(command, 
                shell = shell, 
                capture_output = True)
            if command_output.stderr:
                logging.error("An error occurred during execution of reporting command: {}".format(command_output.stderr.decode(errors='ignore')))
            if command_output.stdout:
                logging.info("Output of reporting command: {}".format(command_output.stdout.decode(errors='ignore')))

    logging.info(" ===== Execution Report ===== \n{}\n ".format(report_string))
    logging.debug(" ========= Perfdata ========= \n{}\n ".format(perfdata_string))

    return(exitcode)


if __name__ == "__main__":

    # Parse arguments:
    for arg_num, arg in enumerate(sys.argv[1:], start=1):
        if arg == "-h" or arg == "--help":
            print(usage)
            sys.exit(0)
        elif arg == "-v" or arg == "--version":
            print("bck_mgmt.py version {}".format(VERSION))
            sys.exit(0)
        elif arg == "-d" or arg == "--debug":
            DEBUG = True
        elif (arg == "-c" or arg == "--conf") and arg_num < len(sys.argv[1:]):
            conf_path = sys.argv[arg_num+1]

    if not conf_path or not Path(conf_path).is_file():
        print("ERROR: No config file specified or config path not found.\n\n" + usage)
        sys.exit(3)

    sys.exit(main(conf_path))
