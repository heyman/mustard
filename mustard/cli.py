import os
import sys
import imp
from .mustard import Project

def main():
    if not os.path.exists("mustardfile.py"):
        sys.stderr.write("No mustardfile.py found in current working directory\n")
        sys.exit(1)
    
    mustardfile = imp.load_source("mustardfile", "mustardfile.py")
    
    if not hasattr(mustardfile, "project"):
        sys.stderr.write("mustardfile.py does not have a project variable\n")
        sys.exit(1)
        
    if not isinstance(mustardfile.project, Project):
        sys.stderr.write("mustardfile.project is not an instance of mustard.Project\n")
        sys.exit(1)
        
    # run CLI
    cli = mustardfile.project.cli()
    cli()

if __name__ == "__main__":
    main()

