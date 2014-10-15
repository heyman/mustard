import os
import time
import subprocess

import click
from fabric.api import task, run, env, settings, open_shell, hide


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
    
    def open_shell(self, command):
        """
        Spawn shell by running local ssh command. 
        Fabric's open_shell() doesn't seem to work when 
        opening shells within docker containers.
        """
        host, port = self.host_string.split(":")
        #subprocess.call(" ".join(["ssh", host, "-t", "-p", port, '"%s"' % command]), shell=True)
        subprocess.call(["ssh", host, "-t", "-p", port, command])
    
    @cmd
    @click.option("-a", default=False, is_flag=True)
    def ps(self, a):
        arg = ["docker", "ps"]
        if a:
            arg.append("-a")
        arg.append("| grep '%s'" % self.name)
        self.run(" ".join(arg))
    
    def cli(self):
        cli = click.Group("mustard")
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
    command = None
    shell_command = None
    shell_links = None
    
    def __init__(self, name, image, volumes={}, env={}, links=[], command=None, shell_command=None, shell_links=None):
        self.name = name
        self.image = image
        self.volumes = volumes
        self.env = env
        self.links = links
        self.command = command
        self.shell_command = shell_command
        self.shell_links = shell_links
    
    @cmd
    def run(self):
        self.project.run("docker %s" % self._run_arguments())
    
    @cmd
    def start(self):
        if self.exists():
            self.project.run("docker start %s" % self.container_name)
        else:
            self.run()
    
    @cmd
    def stop(self):
        self.project.run("docker stop %s" % self.container_name)
    
    @cmd
    def restart(self):
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
        self.project.open_shell(" ".join(arguments))
    
    @cmd
    def pull(self):
        was_running = False
        import sys
        class MyStream(object):
            def write(self, data):
                #print "write:", data, len(data)
                if not data == "[heyevent@127.0.0.1:2222] out: ":
                    sys.stdout.write(data)
            def flush(self):
                sys.stdout.flush()
                pass
        self.project.run("docker pull " + self.image, stdout=MyStream())
        return
        if self.exists():
            was_running = self.is_running()
            if was_running:
                # stop container if running
                self.stop()
            # remove old container
            self.rm()
        if was_running:
            # start container again if it was previously running
            self.run()
    
    @cmd
    def is_running(self):
        response = self.project.run(
            'docker inspect -f "{{ .NetworkSettings.IPAddress }}" %s' % self.container_name,
            quiet=True,
        )
        return bool(response)
    
    @cmd
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
                host_path = "%s/volumes/%s/%s" % (self.project.home_path, self.name, volume_name)
                yield (host_path, container_path)
    
    def _run_arguments(self):
        arguments = []
        arguments.append("-d")
        
        arguments.append("--name=%s" % self.container_name)
        arguments.append(self._run_link_arguments())
        arguments.append(self._run_volume_arguments())
        arguments.append(self._run_env_arguments())
        
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
    
    def _run_env_arguments(service):
        arguments = []
        if service.env:
            for name, value in service.env.iteritems():
                arguments.append("-e %s=%s" % (name, value))
        return " ".join(arguments)
    
    def cli(self):
        cli = click.Group(self.name)
        command_names = filter(lambda n: hasattr(getattr(self, n), "cli_command"), dir(self))
        for name in command_names:
            params = getattr(getattr(self, name), "__click_params__", None)
            cli.add_command(click.Command(name, callback=getattr(self, name), params=params))
        
        if self.shell_command:
            cli.add_command(click.Command("shell", callback=self.shell))
        
        return cli
