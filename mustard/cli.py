import os
import sys
import imp
from .mustard import Project

def main():
    if not os.path.exists("mustardfile.py"):
        sys.stderr.write("No mustardfile.py found in current working directory\n")
        sys.exit(1)
    
    mustardfile = imp.load_source("mustardfile", "mustardfile.py")
    try:
        if not isinstance(mustardfile.project, Project):
            raise TypeError("mustardfile.project not of type mustard.Project")
        cli = mustardfile.project.cli()
    except (AttributeError, TypeError):
        sys.stderr.write("mustardfile.project is not an instance of mustard.Project\n")
        sys.exit(1)
        
    # run CLI
    cli()

if __name__ == "__main__":
    main()

