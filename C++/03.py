from pip._internal.utils.misc import get_installed_distributions
import os
import time

for package in pip.get_installed_distributions():
     print("%s: %s" % (package, time.ctime(os.path.getctime(package.location))))