import os
import time
import subprocess

import click
from fabric.api import task, run, env, settings, hide


def cmd(f):
    """
    Makes methods (on the classes: Project and Service) into CLI commands
    """
    f.cli_command = True
    return f


class Project(object):
    name = None
    host_string = None
    project_user = None
    public_ssh_key = None
    services = []
    
    def __init__(self, name, host_string=None, project_user=None, public_ssh_key=None, services=[]):
        self.name = name
        self.host_string = host_string
        self.project_user = project_user or name
        self.public_ssh_key = public_ssh_key or os.path.expanduser("~/.ssh/id_rsa.pub")
        for service in services:
            self.add_service(service)
    
    def add_service(self, service):
        service.project = self
        self.services.append(service)
    
    def get_service(self, name):
        for service in self.services:
            if service.name == name:
                return service
    
    @property
    def home_path(self):
        return "/home/%s" % self.project_user
    
    def run(self, *args, **kwargs):
        env.host_string = self.host_string
        return run(*args, **kwargs)
    
    def run_ssh(self, command, to_file=None, from_file=None, terminal=True):
        """
        Run a local ssh command
        """
        host, port = self.host_string.split(":")
        args = ["ssh", host]
        if terminal:
            args.append("-t")
        args.extend(["-p", port, command])
        
        ssh_command = subprocess.list2cmdline(args)
        if from_file is not None:
            ssh_command += " < " + from_file
        if to_file is not None:
            ssh_command += " > " + to_file
        #print ssh_command
        os.system(ssh_command)
    
    @cmd
    @click.option("-a", default=False, is_flag=True)
    def ps(self, a):
        arg = ["docker", "ps"]
        if a:
            arg.append("-a")
        arg.append("| grep '%s'" % self.name)
        self.run(" ".join(arg))
    
    def cli(self):
        def set_host(host):
            if host is not None:
                self.host_string = host
        
        cli = click.Group("mustard", params=[click.Option(["--host"], default=None)], callback=set_host)
        for service in self.services:
            cli.add_command(service.cli())
        
        command_names = filter(lambda n: hasattr(getattr(self, n), "cli_command"), dir(self))
        for name in command_names:
            params = getattr(getattr(self, name), "__click_params__", None)
            cli.add_command(click.Command(name, callback=getattr(self, name), params=params))
        
        return cli


class Service(object):
    project = None
    name = None
    image = None
    volumes = None
    env = None
    links = None
    ports = None
    command = None
    shell_command = None
    shell_links = None
    
    def __init__(self, name, image, volumes={}, env={}, links=[], ports=[], command=None, shell_command=None, shell_links=None, registry_login=None):
        self.name = name
        self.image = image
        self.volumes = volumes
        self.env = env
        self.links = links
        self.ports = ports
        self.command = command
        self.shell_command = shell_command
        self.shell_links = shell_links
        self.registry_login = registry_login
    
    @cmd
    def start(self):
        if self.exists():
            self.project.run("docker start %s" % self.container_name)
        else:
            self.project.run("docker %s" % self._run_arguments())
    
    @cmd
    def stop(self):
        self.project.run("docker stop %s" % self.container_name)
    
    @cmd
    def restart(self):
        if not self.exists():
            self.start()
        else:
            self.project.run("docker restart %s" % self.container_name)
    
    @cmd
    def rm(self):
        self.project.run("docker rm %s" % self.container_name)
    
    @cmd
    @click.option("--follow/--no-follow", "-f", default=False)
    def logs(self, follow):
        arguments = ["docker", "logs"]
        if follow:
            arguments.append("-f")
        arguments.append(self.container_name)
        self.project.run(" ".join(arguments))
    
    def shell(self):
        if not self.shell_command:
            return
        arguments = ["docker run --rm -i -t"]
        arguments.append("--name=%s_shell_%i" % (self.container_name, int(time.time()*1000)))
        arguments.append(self._run_link_arguments(self.shell_links))
        arguments.append(self.image)
        arguments.append(self.shell_command)
        self.project.run_ssh(" ".join(arguments))
    
    @cmd
    def pull(self):
        was_running = False
        if self.registry_login is not None:
            self.project.run("docker login " + self.registry_login)
        self.project.run("docker pull " + self.image)
        if self.exists():
            was_running = self.is_running()
            if was_running:
                # stop container if running
                self.stop()
            # remove old container
            self.rm()
        if was_running:
            # start container again if it was previously running
            self.start()
    
    @cmd
    @click.option("--interactive", "-i", default=True, is_flag=True)
    @click.option("--terminal", "-t", default=True, is_flag=True)
    @click.option("--volumes", default=False, is_flag=True)
    @click.argument("command")
    def run(self, command, interactive=True, terminal=True, container_name_suffix="cmd", volumes=False):
        args = ["docker run --rm"]
        
        if interactive:
            args.append("-i")
        if terminal:
            args.append("-t")
        
        args.append("--name=%s_%s_%i" % (self.container_name, container_name_suffix, int(time.time()*1000)))
        args.append(self._run_link_arguments(self.shell_links))
        args.append(self._run_env_arguments())
        if volumes:
            args.append(self._run_volume_arguments())
        args.append(self.image)
        args.append(command)
        
        self.project.run(" ".join(args))
    
    def is_running(self):
        response = self.project.run(
            'docker inspect -f "{{ .NetworkSettings.IPAddress }}" %s' % self.container_name,
            quiet=True,
        )
        return bool(response)
    
    def exists(self):
        response = self.project.run(
            'docker inspect -f "{{ .NetworkSettings.IPAddress }}" %s' % self.container_name,
            quiet=True,
        )
        return response.return_code == 0
    
    @property
    def container_name(self):
        return self.project.name  + "_" + self.name
    
    def _iter_volumes(self):
        """
        Yields (host_path, container_path) tuple for every volume in a service
        """
        if self.volumes:
            for volume_name, container_path in self.volumes.iteritems():
                if "/" in volume_name:
                    # if a / is found in the name, assume it's a full path specified on the host
                    host_path = volume_name
                else:
                    host_path = "%s/volumes/%s/%s" % (self.project.home_path, self.name, volume_name)
                yield (host_path, container_path)
    
    def _run_arguments(self):
        arguments = []
        arguments.append("-d")
        
        arguments.append("--name=%s" % self.container_name)
        arguments.append(self._run_link_arguments())
        arguments.append(self._run_volume_arguments())
        arguments.append(self._run_env_arguments())
        arguments.append(self._run_ports_arguments())
        
        arguments.append(self.image)
        if self.command:
            arguments.append(self.command)
        
        return "run %s" % " ".join(arguments)
    
    def _run_link_arguments(self, links=None):
        if not links:
            links = self.links
        arguments = []
        if links:
            for target_service in links:
                if isinstance(target_service, basestring):
                    target_service = self.project.get_service(target_service)
                arguments.append("--link=%s:%s" % (target_service.container_name, target_service.name))
        return " ".join(arguments)
    
    def _run_volume_arguments(self):
        arguments = []
        for host_path, container_path in self._iter_volumes():
            arguments.append("-v %s:%s" % (host_path, container_path))
        return " ".join(arguments)
    
    def _run_env_arguments(self):
        arguments = []
        if self.env:
            for name, value in self.env.iteritems():
                arguments.append("-e %s=%s" % (name, value))
        return " ".join(arguments)
    
    def _run_ports_arguments(self):
        args = []
        if self.ports:
            for host_port, container_port in self.ports.iteritems():
                args.append("-p %s:%s" % (host_port, container_port))
        return " ".join(args)
    
    def cli(self):
        cli = click.Group(self.name)
        command_names = filter(lambda n: hasattr(getattr(self, n), "cli_command"), dir(self))
        for name in command_names:
            params = getattr(getattr(self, name), "__click_params__", None)
            cli.add_command(click.Command(name, callback=getattr(self, name), params=params))
        
        if self.shell_command:
            cli.add_command(click.Command("shell", callback=self.shell))
        
        return cli
