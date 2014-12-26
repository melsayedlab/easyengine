"""Example Plugin for EasyEngine."""

from cement.core.controller import CementBaseController, expose
from cement.core import handler, hook
from ee.core.variables import EEVariables
from ee.core.aptget import EEAptGet
from ee.core.download import EEDownload
from ee.core.shellexec import EEShellExec
from ee.core.fileutils import EEFileUtils
from ee.core.apt_repo import EERepo
from ee.core.extract import EEExtract
from ee.core.mysql import EEMysql
from pynginxconfig import NginxConfig
import random
import string
import configparser
import time
import shutil
import os
import pwd
import grp
from ee.cli.plugins.stack_services import EEStackStatusController


def ee_stack_hook(app):
    # do something with the ``app`` object here.
    pass


class EEStackController(CementBaseController):
    class Meta:
        label = 'stack'
        stacked_on = 'base'
        stacked_type = 'nested'
        description = 'stack command manages stack operations'
        arguments = [
            (['--web'],
                dict(help='Install web stack', action='store_true')),
            (['--admin'],
                dict(help='Install admin tools stack', action='store_true')),
            (['--mail'],
                dict(help='Install mail server stack', action='store_true')),
            (['--nginx'],
                dict(help='Install Nginx stack', action='store_true')),
            (['--php'],
                dict(help='Install PHP stack', action='store_true')),
            (['--mysql'],
                dict(help='Install MySQL stack', action='store_true')),
            (['--postfix'],
                dict(help='Install Postfix stack', action='store_true')),
            (['--wpcli'],
                dict(help='Install WPCLI stack', action='store_true')),
            (['--phpmyadmin'],
                dict(help='Install PHPMyAdmin stack', action='store_true')),
            (['--adminer'],
                dict(help='Install Adminer stack', action='store_true')),
            (['--utils'],
                dict(help='Install Utils stack', action='store_true')),
            ]

    @expose(hide=True)
    def default(self):
        # TODO Default action for ee stack command
        print("Inside EEStackController.default().")

    @expose(hide=True)
    def pre_pref(self, apt_packages):
        if set(EEVariables.ee_postfix).issubset(set(apt_packages)):
            print("Pre-seeding postfix variables ... ")
            EEShellExec.cmd_exec("echo \"postfix postfix/main_mailer_type "
                                 "string 'Internet Site'\" | "
                                 "debconf-set-selections")
            EEShellExec.cmd_exec("echo \"postfix postfix/mailname string "
                                 "$(hostname -f)\" | debconf-set-selections")
        if set(EEVariables.ee_mysql).issubset(set(apt_packages)):
            print("Adding repository for mysql ... ")
            EERepo.add(repo_url=EEVariables.ee_mysql_repo)
            EERepo.add_key('1C4CBDCDCD2EFD2A')
            chars = ''.join(random.sample(string.ascii_letters, 8))
            print("Pre-seeding mysql variables ... ")
            EEShellExec.cmd_exec("echo \"percona-server-server-5.6 "
                                 "percona-server-server/root_password "
                                 "password {chars}\" | "
                                 "debconf-set-selections".format(chars=chars))
            EEShellExec.cmd_exec("echo \"percona-server-server-5.6 "
                                 "percona-server-server/root_password_again "
                                 "password {chars}\" | "
                                 "debconf-set-selections".format(chars=chars))
            mysql_config = """
            [mysqld]
            user = root
            password = {chars}
            """.format(chars=chars)
            config = configparser.ConfigParser()
            config.read_string(mysql_config)
            with open(os.path.expanduser("~")+'/.my.cnf', 'w') as configfile:
                config.write(configfile)

        if set(EEVariables.ee_nginx).issubset(set(apt_packages)):
            print("Adding repository for nginx ... ")
            if EEVariables.ee_platform_distro == 'Debian':
                EERepo.add(repo_url=EEVariables.ee_nginx_repo)
            else:
                EERepo.add(ppa=EEVariables.ee_nginx_repo)

        if set(EEVariables.ee_php).issubset(set(apt_packages)):
            print("Adding repository for php ... ")
            if EEVariables.ee_platform_distro == 'Debian':
                EERepo.add(repo_url=EEVariables.ee_php_repo)
                EERepo.add_key('89DF5277')
            else:
                EERepo.add(ppa=EEVariables.ee_php_repo)

        if set(EEVariables.ee_mail).issubset(set(apt_packages)):
            if EEVariables.ee_platform_codename == 'squeeze':
                print("Adding repository for dovecot ... ")
                EERepo.add(repo_url=EEVariables.ee_dovecot_repo)

            EEShellExec.cmd_exec("echo \"dovecot-core dovecot-core/"
                                 "create-ssl-cert boolean yes\" "
                                 "| debconf-set-selections")
            EEShellExec.cmd_exec("echo \"dovecot-core dovecot-core/ssl-cert-"
                                 "name string $(hostname -f)\""
                                 " | debconf-set-selections")

    @expose(hide=True)
    def post_pref(self, apt_packages, packages):
        if len(apt_packages):
            if set(EEVariables.ee_postfix).issubset(set(apt_packages)):
                pass
            if set(EEVariables.ee_nginx).issubset(set(apt_packages)):
                # Nginx core configuration change using configparser
                nc = NginxConfig()
                print('in nginx')
                nc.loadf('/etc/nginx/nginx.conf')
                nc.set('worker_processes', 'auto')
                nc.append(('worker_rlimit_nofile', '100000'), position=2)
                nc.remove(('events', ''))
                nc.append({'name': 'events', 'param': '', 'value':
                           [('worker_connections', '4096'),
                            ('multi_accept', 'on')]}, position=4)
                nc.set([('http',), 'keepalive_timeout'], '30')
                nc.savef('/etc/nginx/nginx.conf')

                # Custom Nginx configuration by EasyEngine
                data = dict(version='EasyEngine 3.0.1')
                ee_nginx = open('/etc/nginx/conf.d/ee-nginx.conf', 'w')
                self.app.render((data), 'nginx-core.mustache', out=ee_nginx)
                ee_nginx.close()

            if set(EEVariables.ee_php).issubset(set(apt_packages)):
                # Parse etc/php5/fpm/php.ini
                config = configparser.ConfigParser()
                config.read('/etc/php5/fpm/php.ini')
                config['PHP']['expose_php'] = 'Off'
                config['PHP']['post_max_size'] = '100M'
                config['PHP']['upload_max_filesize'] = '100M'
                config['PHP']['max_execution_time'] = '300'
                config['PHP']['date.timezone'] = time.tzname[time.daylight]
                with open('/etc/php5/fpm/php.ini', 'w') as configfile:
                    config.write(configfile)

                # Prase /etc/php5/fpm/php-fpm.conf
                config = configparser.ConfigParser()
                config.read('/etc/php5/fpm/php-fpm.conf')
                config['global']['error_log'] = '/var/log/php5/fpm.log'
                with open('/etc/php5/fpm/php-fpm.conf', 'w') as configfile:
                    config.write(configfile)

                # Parse /etc/php5/fpm/pool.d/www.conf
                config = configparser.ConfigParser()
                config.read('/etc/php5/fpm/pool.d/www.conf')
                config['www']['ping.path'] = '/ping'
                config['www']['pm.status_path'] = '/status'
                config['www']['pm.max_requests'] = '500'
                config['www']['pm.max_children'] = ''
                config['www']['pm.start_servers'] = '20'
                config['www']['pm.min_spare_servers'] = '10'
                config['www']['pm.max_spare_servers'] = '30'
                config['www']['request_terminate_timeout'] = '300'
                config['www']['pm'] = 'ondemand'
                config['www']['listen'] = '127.0.0.1:9000'
                with open('/etc/php5/fpm/pool.d/www.conf', 'w') as configfile:
                    config.write(configfile)

            if set(EEVariables.ee_mysql).issubset(set(apt_packages)):
                config = configparser.ConfigParser()
                config.read('/etc/mysql/my.cnf')
                config['mysqld']['wait_timeout'] = 30
                config['mysqld']['interactive_timeout'] = 60
                config['mysqld']['performance_schema'] = 0
                with open('/etc/mysql/my.cnf', 'w') as configfile:
                    config.write(configfile)

            if set(EEVariables.ee_mail).issubset(set(apt_packages)):
                EEShellExec.cmd_exec("adduser --uid 5000 --home /var/vmail"
                                     "--disabled-password --gecos '' vmail")
                EEShellExec.cmd_exec("openssl req -new -x509 -days 3650 -nodes"
                                     " -subj /commonName={HOSTNAME}/emailAddre"
                                     "ss={EMAIL} -out /etc/ssl/certs/dovecot."
                                     "pem -keyout /etc/ssl/private/dovecot.pem"
                                     .format(HOSTNAME=EEVariables.ee_fqdn,
                                             EMAIL=EEVariables.ee_email))
                EEShellExec.cmd_exec("chmod 0600 /etc/ssl/private/dovecot.pem")

                # Custom Dovecot configuration by EasyEngine
                data = dict()
                ee_dovecot = open('/etc/dovecot/conf.d/99-ee.conf', 'w')
                self.app.render((data), 'dovecot.mustache', out=ee_dovecot)
                ee_dovecot.close()

                # Custom Postfix configuration needed with Dovecot
                # Changes in master.cf
                # TODO: Find alternative for sed in Python
                EEShellExec.cmd_exec("sed -i \'s/#submission/submission/\'"
                                     " /etc/postfix/master.cf")
                EEShellExec.cmd_exec("sed -i \'s/#smtps/smtps/\'"
                                     " /etc/postfix/master.cf")

                EEShellExec.cmd_exec("postconf -e \"smtpd_sasl_type = "
                                     "dovecot\"")
                EEShellExec.cmd_exec("postconf -e \"smtpd_sasl_path = "
                                     "private/auth\"")
                EEShellExec.cmd_exec("postconf -e \"smtpd_sasl_auth_enable = "
                                     "yes\"")
                EEShellExec.cmd_exec("postconf -e \"smtpd_relay_restrictions ="
                                     " permit_sasl_authenticated, "
                                     "permit_mynetworks, "
                                     "reject_unauth_destination\"")
                EEShellExec.cmd_exec("postconf -e \"smtpd_tls_mandatory_"
                                     "protocols = !SSLv2,!SSLv3\"")
                EEShellExec.cmd_exec("postconf -e \"smtp_tls_mandatory_"
                                     "protocols = !SSLv2,!SSLv3\"")
                EEShellExec.cmd_exec("postconf -e \"smtpd_tls_protocols "
                                     "= !SSLv2,!SSLv3\"")
                EEShellExec.cmd_exec("postconf -e \"smtp_tls_protocols "
                                     "= !SSLv2,!SSLv3\"")
                EEShellExec.cmd_exec("postconf -e \"mydestination "
                                     "= localhost\"")
                EEShellExec.cmd_exec("postconf -e \"virtual_transport "
                                     "= lmtp:unix:private/dovecot-lmtp\"")
                EEShellExec.cmd_exec("postconf -e \"virtual_uid_maps "
                                     "= static:5000\"")
                EEShellExec.cmd_exec("postconf -e \"virtual_gid_maps "
                                     "= static:5000\"")
                EEShellExec.cmd_exec("postconf -e \"virtual_mailbox_domains = "
                                     "mysql:/etc/postfix/mysql/virtual_"
                                     "domains_maps.cf\"")
                EEShellExec.cmd_exec("postconf -e \"virtual_mailbox_maps = "
                                     "mysql:/etc/postfix/mysql/virtual_"
                                     "mailbox_maps.cf\"")
                EEShellExec.cmd_exec("postconf -e \"virtual_alias_maps = "
                                     "mysql:/etc/postfix/mysql/virtual_"
                                     "alias_maps.cf\"")
                EEShellExec.cmd_exec("openssl req -new -x509 -days 3650 -nodes"
                                     " -subj /commonName={HOSTNAME}/emailAddre"
                                     "ss={EMAIL} -out /etc/ssl/certs/postfix."
                                     "pem -keyout /etc/ssl/private/postfix.pem"
                                     .format(HOSTNAME=EEVariables.ee_fqdn,
                                             EMAIL=EEVariables.ee_email))
                EEShellExec.cmd_exec("chmod 0600 /etc/ssl/private/postfix.pem")
                EEShellExec.cmd_exec("postconf -e \"smtpd_tls_cert_file = "
                                     "/etc/ssl/certs/postfix.pem\"")
                EEShellExec.cmd_exec("postconf -e \"smtpd_tls_key_file = "
                                     "/etc/ssl/private/postfix.pem\"")

                # Sieve configuration
                if not os.path.exists('/var/lib/dovecot/sieve/'):
                    os.makedirs('/var/lib/dovecot/sieve/')

                # Custom sieve configuration by EasyEngine
                data = dict()
                ee_sieve = open('/var/lib/dovecot/sieve/default.sieve', 'w')
                self.app.render((data), 'default-sieve.mustache',
                                out=ee_sieve)
                ee_sieve.close()

                # Compile sieve rules
                EEShellExec.cmd_exec("chown -R vmail:vmail /var/lib/dovecot")
                EEShellExec.cmd_exec("sievec /var/lib/dovecot/sieve/"
                                     "default.sieve")

            if set(EEVariables.ee_mailscanner).issubset(set(apt_packages)):
                # Set up Custom amavis configuration
                data = dict()
                ee_amavis = open('/etc/amavis/conf.d/15-content_filter_mode',
                                 'w')
                self.app.render((data), '15-content_filter_mode.mustache',
                                out=ee_amavis)
                ee_amavis.close()

                # Amavis postfix configuration
                EEShellExec.cmd_exec("postconf -e \"content_filter = "
                                     "smtp-amavis:[127.0.0.1]:10024\"")
                EEShellExec.cmd_exec("sed -i \"s/1       pickup/1       pickup"
                                     "\n        -o content_filter=\n        -o"
                                     " receive_override_options=no_header_body"
                                     "_checks/\" /etc/postfix/master.cf")

                # Amavis ClamAV configuration
                EEShellExec.cmd_exec("adduser clamav amavis")
                EEShellExec.cmd_exec("adduser amavis clamav")
                EEShellExec.cmd_exec("chmod -R 775 /var/lib/amavis/tmp")

                # Update ClamAV database
                EEShellExec.cmd_exec("freshclam")
                EEShellExec.cmd_exec("service clamav-daemon restart")

        if len(packages):
            if any('/usr/bin/wp' == x[1] for x in packages):

                EEShellExec.cmd_exec("chmod +x /usr/bin/wp")
            if any('/tmp/pma.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/pma.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/db'):
                    os.makedirs('/var/www/22222/htdocs/db')
                shutil.move('/tmp/phpmyadmin-STABLE/',
                            '/var/www/22222/htdocs/db/pma/')
                EEShellExec.cmd_exec('chown -R www-data:www-data '
                                     '/var/www/22222/htdocs/db/pma')
            if any('/tmp/memcache.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/memcache.tar.gz',
                                  '/var/www/22222/htdocs/cache/memcache')
                EEShellExec.cmd_exec('chown -R www-data:www-data '
                                     '/var/www/22222/htdocs/cache/memcache')

            if any('/tmp/webgrind.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/webgrind.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/php'):
                    os.makedirs('/var/www/22222/htdocs/php')
                shutil.move('/tmp/webgrind-master/',
                            '/var/www/22222/htdocs/php/webgrind')
                EEShellExec.cmd_exec('chown -R www-data:www-data '
                                     '/var/www/22222/htdocs/php/webgrind/')

            if any('/tmp/anemometer.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/anemometer.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/db/'):
                    os.makedirs('/var/www/22222/htdocs/db/')
                shutil.move('/tmp/Anemometer-master',
                            '/var/www/22222/htdocs/db/anemometer')
                chars = ''.join(random.sample(string.ascii_letters, 8))
                EEShellExec.cmd_exec('mysql < /var/www/22222/htdocs/db'
                                     '/anemometer/install.sql')
                EEMysql.execute('grant select on *.* to \'anemometer\''
                                '@\'localhost\'')
                EEMysql.execute('grant all on slow_query_log.* to'
                                '\'anemometer\'@\'localhost\' IDENTIFIED'
                                ' BY \''+chars+'\'')

                # Custom Anemometer configuration
                data = dict(host='localhost', port='3306', user='anemometer',
                            password=chars)
                ee_anemometer = open('/var/www/22222/htdocs/db/anemometer'
                                     '/conf/config.inc.php', 'w')
                self.app.render((data), 'anemometer.mustache',
                                out=ee_anemometer)
                ee_anemometer.close()

            if any('/usr/bin/pt-query-advisor' == x[1]
                    for x in packages):
                EEShellExec.cmd_exec("chmod +x /usr/bin/pt-query-advisor")

            if any('/tmp/vimbadmin.tar.gz' == x[1] for x in packages):
                # Extract ViMbAdmin
                EEExtract.extract('/tmp/vimbadmin.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/'):
                    os.makedirs('/var/www/22222/htdocs/')
                shutil.move('/tmp/ViMbAdmin-3.0.10/',
                            '/var/www/22222/htdocs/vimbadmin/')

                # Donwload composer and install ViMbAdmin
                EEShellExec.cmd_exec("cd /var/www/22222/htdocs/vimbadmin; curl"
                                     " -sS https://getcomposer.org/installer |"
                                     " php")
                EEShellExec.cmd_exec("cd /var/www/22222/htdocs/vimbadmin && "
                                     "php composer.phar install --prefer-dist"
                                     " --no-dev && rm -f /var/www/22222/htdocs"
                                     "/vimbadmin/composer.phar")

                # Configure vimbadmin database
                vm_passwd = ''.join(random.sample(string.ascii_letters, 8))

                EEMysql.execute("create database if not exists vimbadmin")
                EEMysql.execute("grant all privileges on vimbadmin.* to"
                                " vimbadmin@localhost IDENTIFIED BY"
                                " '{password}'".format(password=vm_passwd))

                # Configure ViMbAdmin settings
                config = configparser.ConfigParser(strict=False)
                config.read('/var/www/22222/htdocs/vimbadmin/application/'
                            'configs/application.ini.dist')
                config['user']['defaults.mailbox.uid'] = '5000'
                config['user']['defaults.mailbox.gid'] = '5000'
                config['user']['defaults.mailbox.maildir'] = ("maildir:/var/v"
                                                              + "mail/%%d/%%u")
                config['user']['defaults.mailbox.homedir'] = ("/srv/vmail/"
                                                              + "%%d/%%u")
                config['user']['resources.doctrine2.connection.'
                               'options.driver'] = 'mysqli'
                config['user']['resources.doctrine2.connection.'
                               'options.password'] = vm_passwd
                config['user']['resources.doctrine2.connection.'
                               'options.host'] = 'localhost'
                config['user']['defaults.mailbox.password_scheme'] = 'md5'
                config['user']['securitysalt'] = (''.join(random.sample
                                                  (string.ascii_letters
                                                   + string.ascii_letters,
                                                   64)))
                config['user']['resources.auth.'
                               'oss.rememberme.salt'] = (''.join(random.sample
                                                         (string.ascii_letters
                                                          + string.
                                                             ascii_letters,
                                                          64)))
                config['user']['defaults.mailbox.'
                               'password_salt'] = (''.join(random.sample
                                                   (string.ascii_letters
                                                    + string.ascii_letters,
                                                    64)))
                with open('/var/www/22222/htdocs/vimbadmin/application'
                          '/configs/application.ini', 'w') as configfile:
                    config.write(configfile)

                shutil.copyfile("/var/www/22222/htdocs/vimbadmin/public/"
                                ".htaccess.dist",
                                "/var/www/22222/htdocs/vimbadmin/public/"
                                ".htaccess")
                EEShellExec.cmd_exec("/var/www/22222/htdocs/vimbadmin/bin"
                                     "/doctrine2-cli.php orm:schema-tool:"
                                     "create")

                # Copy Dovecot and Postfix templates which are depednet on
                # Vimbadmin
                if not os.path.exists('/etc/postfix/mysql/'):
                    os.makedirs('/etc/postfix/mysql/')
                data = dict(password=vm_passwd)
                vm_config = open('/etc/postfix/mysql/virtual_alias_maps.cf',
                                 'w')
                self.app.render((data), 'virtual_alias_maps.mustache',
                                out=vm_config)
                vm_config.close()

                vm_config = open('/etc/postfix/mysql/virtual_domains_maps.cf',
                                 'w')
                self.app.render((data), 'virtual_domains_maps.mustache',
                                out=vm_config)
                vm_config.close()

                vm_config = open('/etc/postfix/mysql/virtual_mailbox_maps.cf',
                                 'w')
                self.app.render((data), 'virtual_mailbox_maps.mustache',
                                out=vm_config)
                vm_config.close()

                vm_config = open('/etc/dovecot/dovecot-sql.conf.ext',
                                 'w')
                self.app.render((data), 'dovecot-sql-conf.mustache',
                                out=vm_config)
                vm_config.close()

                # If Amavis is going to be installed then configure Vimabadmin
                # Amvis settings
                if set(EEVariables.ee_mailscanner).issubset(set(apt_packages)):
                    vm_config = open('/etc/amavis/conf.d/50-user',
                                     'w')
                    self.app.render((data), '50-user.mustache',
                                    out=vm_config)
                    vm_config.close()

            if any('/tmp/roundcube.tar.gz' == x[1] for x in packages):
                # Extract RoundCubemail
                EEExtract.extract('/tmp/roundcube.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/roundcubemail'):
                    os.makedirs('/var/www/roundcubemail/')
                shutil.move('/tmp/roundcubemail-1.0.4/',
                            '/var/www/roundcubemail/htdocs')

                # Configure roundcube database
                rc_passwd = ''.join(random.sample(string.ascii_letters, 8))
                EEMysql.execute("create database if not exists roundcubemail")
                EEMysql.execute("grant all privileges on roundcubemail.* to "
                                " roundcube@localhost IDENTIFIED BY "
                                "'{password}'".format(password=rc_passwd))
                EEShellExec.cmd_exec("mysql roundcubemail < /var/www/"
                                     "roundcubemail/htdocs/SQL/mysql"
                                     ".initial.sql")

                shutil.copyfile("/var/www/roundcubemail/htdocs/config/"
                                "config.inc.php.sample",
                                "/var/www/roundcubemail/htdocs/config/"
                                "config.inc.php")
                EEShellExec.cmd_exec("sed -i \"s\'mysql://roundcube:pass@"
                                     "localhost/roundcubemail\'mysql://"
                                     "roundcube:{password}@localhost/"
                                     "roundcubemail\'\" /var/www/roundcubemail"
                                     "/htdocs/config/config."
                                     "inc.php".format(password=rc_passwd))

                # Sieve plugin configuration in roundcube
                EEShellExec.cmd_exec("sed -i \"s:\$config\['plugins'\] = array"
                                     "(:\$config\['plugins'\] = array(\n "
                                     "'sieverules',:\" /var/www/roundcubemail"
                                     "/htdocs/config/config.inc.php")
                EEShellExec.cmd_exec("echo \"\$config['sieverules_port'] = "
                                     "4190;\" >> /var/www/roundcubemail/htdocs"
                                     "/config/config.inc.php")

    @expose()
    def install(self):
        pkg = EEAptGet()
        apt_packages = []
        packages = []

        if self.app.pargs.web:
            apt_packages = (apt_packages + EEVariables.ee_nginx +
                            EEVariables.ee_php + EEVariables.ee_mysql)

        if self.app.pargs.admin:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.mail:
            apt_packages = apt_packages + EEVariables.ee_mail
            packages = packages + [["https://github.com/opensolutions/ViMbAdmi"
                                    "n/archive/3.0.10.tar.gz", "/tmp/vimbadmin"
                                    ".tar.gz"],
                                   ["https://github.com/roundcube/"
                                    "roundcubemail/releases/download/"
                                    "1.0.4/roundcubemail-1.0.4.tar.gz",
                                    "/tmp/roundcube.tar.gz"]
                                   ]
            if EEVariables.ee_ram > 1024:
                apt_packages = apt_packages + EEVariables.ee_mailscanner

        if self.app.pargs.nginx:
            apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.php:
            apt_packages = apt_packages + EEVariables.ee_php
        if self.app.pargs.mysql:
            apt_packages = apt_packages + EEVariables.ee_mysql
        if self.app.pargs.postfix:
            apt_packages = apt_packages + EEVariables.ee_postfix
        if self.app.pargs.wpcli:
            packages = packages + [["https://github.com/wp-cli/wp-cli/releases"
                                    "/download/v0.17.1/wp-cli.phar",
                                    "/usr/bin/wp"]]
        if self.app.pargs.phpmyadmin:
            packages = packages + [["https://github.com/phpmyadmin/phpmyadmin"
                                    "/archive/STABLE.tar.gz",
                                    "/tmp/pma.tar.gz"]]

        if self.app.pargs.adminer:
            packages = packages + [["http://downloads.sourceforge.net/adminer"
                                    "/adminer-4.1.0.php", "/var/www/22222/"
                                    "htdocs/db/adminer/index.php"]]

        if self.app.pargs.utils:
            packages = packages + [["http://phpmemcacheadmin.googlecode.com/"
                                    "files/phpMemcachedAdmin-1.2.2"
                                    "-r262.tar.gz", '/tmp/memcache.tar.gz'],
                                   ["https://raw.githubusercontent.com/rtCamp/"
                                    "eeadmin/master/cache/nginx/clean.php",
                                    "/var/www/22222/htdocs/cache/"
                                    "nginx/clean.php"],
                                   ["https://raw.github.com/rlerdorf/opcache-"
                                    "status/master/opcache.php",
                                    "/var/www/22222/htdocs/cache/"
                                    "opcache/opcache.php"],
                                   ["https://raw.github.com/amnuts/opcache-gui"
                                    "/master/index.php",
                                    "/var/www/22222/htdocs/"
                                    "cache/opcache/opgui.php"],
                                   ["https://gist.github.com/ck-on/4959032/raw"
                                    "/0b871b345fd6cfcd6d2be030c1f33d1ad6a475cb"
                                    "/ocp.php",
                                    "/var/www/22222/htdocs/cache/"
                                    "opcache/ocp.php"],
                                   ["https://github.com/jokkedk/webgrind/"
                                    "archive/master.tar.gz",
                                    '/tmp/webgrind.tar.gz'],
                                   ["http://bazaar.launchpad.net/~percona-too"
                                    "lkit-dev/percona-toolkit/2.1/download/he"
                                    "ad:/ptquerydigest-20110624220137-or26tn4"
                                    "expb9ul2a-16/pt-query-digest",
                                    "/usr/bin/pt-query-advisor"],
                                   ["https://github.com/box/Anemometer/archive"
                                    "/master.tar.gz",
                                    '/tmp/anemometer.tar.gz']
                                   ]

        self.pre_pref(apt_packages)
        if len(apt_packages):
            pkg.install(apt_packages)
        if len(packages):
            EEDownload.download(packages)
        self.post_pref(apt_packages, packages)

    @expose()
    def remove(self):
        pkg = EEAptGet()
        apt_packages = []
        packages = []

        if self.app.pargs.web:
            apt_packages = (apt_packages + EEVariables.ee_nginx +
                            EEVariables.ee_php + EEVariables.ee_mysql)
        if self.app.pargs.admin:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.mail:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.nginx:
            apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.php:
            apt_packages = apt_packages + EEVariables.ee_php
        if self.app.pargs.mysql:
            apt_packages = apt_packages + EEVariables.ee_mysql
        if self.app.pargs.postfix:
            apt_packages = apt_packages + EEVariables.ee_postfix
        if self.app.pargs.wpcli:
            packages = packages + ['/usr/bin/wp']
        if self.app.pargs.phpmyadmin:
            packages = packages + ['/var/www/22222/htdocs/db/pma']
        if self.app.pargs.adminer:
            packages = packages + ['/var/www/22222/htdocs/db/adminer']
        if self.app.pargs.utils:
            packages = packages + ['/var/www/22222/htdocs/php/webgrind/',
                                   '/var/www/22222/htdocs/cache/opcache',
                                   '/var/www/22222/htdocs/cache/nginx/'
                                   'clean.php',
                                   '/var/www/22222/htdocs/cache/memcache',
                                   '/usr/bin/pt-query-advisor',
                                   '/var/www/22222/htdocs/db/anemometer']

        if len(apt_packages):
            pkg.remove(apt_packages)
        if len(packages):
            EEFileUtils.remove(packages)

    @expose()
    def purge(self):
        pkg = EEAptGet()
        apt_packages = []
        packages = []

        if self.app.pargs.web:
            apt_packages = (apt_packages + EEVariables.ee_nginx
                            + EEVariables.ee_php + EEVariables.ee_mysql)
        if self.app.pargs.admin:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.mail:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.nginx:
            apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.php:
            apt_packages = apt_packages + EEVariables.ee_php
        if self.app.pargs.mysql:
            apt_packages = apt_packages + EEVariables.ee_mysql
        if self.app.pargs.postfix:
            apt_packages = apt_packages + EEVariables.ee_postfix
        if self.app.pargs.wpcli:
            packages = packages + ['/usr/bin/wp']
        if self.app.pargs.phpmyadmin:
            packages = packages + ['/var/www/22222/htdocs/db/pma']
        if self.app.pargs.adminer:
            packages = packages + ['/var/www/22222/htdocs/db/adminer']
        if self.app.pargs.utils:
            packages = packages + ['/var/www/22222/htdocs/php/webgrind/',
                                   '/var/www/22222/htdocs/cache/opcache',
                                   '/var/www/22222/htdocs/cache/nginx/'
                                   'clean.php',
                                   '/var/www/22222/htdocs/cache/memcache',
                                   '/usr/bin/pt-query-advisor',
                                   '/var/www/22222/htdocs/db/anemometer'
                                   ]

        if len(apt_packages):
            pkg.remove(apt_packages, purge=True)
        if len(packages):
            EEFileUtils.remove(packages)


def load(app):
    # register the plugin class.. this only happens if the plugin is enabled
    handler.register(EEStackController)
    handler.register(EEStackStatusController)

    # register a hook (function) to run after arguments are parsed.
    hook.register('post_argument_parsing', ee_stack_hook)