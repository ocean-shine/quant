import re

p = re.compile('ab*')
print(p.search('aabb'))

p = re.compile('ab+')
print(p.search('aabb'))

