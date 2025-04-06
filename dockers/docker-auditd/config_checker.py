#!/usr/bin/env python3

import json
import subprocess
from sonic_py_common import logger as log

logger = log.Logger()


RULES_DIR = "/etc/audit/rules.d/"
SYSLOG_CONF = "/etc/audit/plugins.d/syslog.conf"
AUDIT_CONF = "/etc/audit/auditd.conf"
AUDIT_SERVICE = "/lib/systemd/system/auditd.service"
CONFIG_FILES = "/usr/share/sonic/auditd_config_files/"

RULES_HASH_CMD = r"""find {} -type f -name "[0-9][0-9]-*.rules" \
! -name "30-audisp-tacplus.rules" \
-exec cat {{}} + | \
sort | \
sha1sum""".format(RULES_DIR)
AUDIT_CONF_HASH_CMD = "cat {} | sha1sum".format(AUDIT_CONF)


def run_command(cmd):
    p = subprocess.Popen(cmd,
                         text=True,
                         shell=True, # nosemgrep
                         executable='/bin/bash',
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    output, error = p.communicate()
    if p.returncode == 0:
        return p.returncode, output
    return p.returncode, error


def get_hwsku():
    with open("/etc/sonic/config_db.json") as fp:
        config_db = json.load(fp)
    if "DEVICE_METADATA" in config_db and "hwsku" in config_db["DEVICE_METADATA"]["localhost"]:
        return str(config_db['DEVICE_METADATA']['localhost']['hwsku'])
    return None


def is_auditd_rules_configured():
    EXPECTED_HASH = "f88174f901ec8709bacaf325158f10ec62909d13"
    NOKIA_EXPECTED_HASH = "bd574779fb4e1116838d18346187bb7f7bd089c9"
    hwsku = get_hwsku()
    if "Nokia-7215" in hwsku or "Nokia-M0-7215" in hwsku:
        EXPECTED_HASH = NOKIA_EXPECTED_HASH

    rc, out = run_command(RULES_HASH_CMD)
    is_configured = EXPECTED_HASH in out
    logger.log_info("auditd rules are already configured" if is_configured else "auditd rules are not configured")
    return is_configured


def is_syslog_conf_configured():
    rc, out = run_command("grep '^active = yes' {}".format(SYSLOG_CONF))
    is_configured = rc == 0
    logger.log_info("syslog.conf is already configured" if is_configured else "syslog.conf is not configured")
    return is_configured


def is_auditd_conf_configured():
    rc, out = run_command(AUDIT_CONF_HASH_CMD)
    is_configured = "7cdbd1450570c7c12bdc67115b46d9ae778cbd76" in out
    logger.log_info("auditd.conf is already configured" if is_configured else "auditd.conf is not configured")
    return is_configured


def is_auditd_service_configured():
    rc, out = run_command("grep '^CPUQuota=10%' {}".format(AUDIT_SERVICE))
    is_configured = rc == 0
    logger.log_info("auditd.service is already configured" if is_configured else "auditd.service is not configured")
    return is_configured


def main():
    is_configured = True
    hwsku = get_hwsku()
    if not is_auditd_rules_configured():
        run_command("rm -f {}/*.rules".format(RULES_DIR))
        run_command("cp {}/*.rules {}".format(CONFIG_FILES, RULES_DIR))
        if "Nokia-7215" in hwsku or "Nokia-M0-7215" in hwsku:
            run_command("cp {}/32bit/*.rules {}".format(CONFIG_FILES, RULES_DIR))
        is_configured = False

    if not is_syslog_conf_configured():
        run_command("sed -i 's/^active = no/active = yes/' {}".format(SYSLOG_CONF))
        is_configured = False

    if not is_auditd_conf_configured():
        run_command("cp {}/auditd.conf {}".format(CONFIG_FILES, AUDIT_CONF))
        is_configured = False

    if not is_auditd_service_configured():
        run_command(r"""sed -i '/\[Service\]/a CPUQuota=10%' {}""".format(AUDIT_SERVICE))
        is_configured = False

    if not is_configured:
        run_command("nsenter --target 1 --pid --mount --uts --ipc --net systemctl daemon-reload")
        run_command("nsenter --target 1 --pid --mount --uts --ipc --net systemctl restart auditd")


if __name__ == "__main__":
    main()
