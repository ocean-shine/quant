import time

# file = open(r'./t01.txt', 'a')
# file.write('\n123456789')
# time.sleep(5)
# file.close()
#
# file=open(r'./t01.txt', 'a')
# file.write('\n123456789')
# file.flush()
# time.sleep(5)
# file.close()


tup = ('a\n', 'b\n', 'c\n', 'def')
with open(r'./t01.txt', 'w') as f:
    f.writelines(tup)

with open(r'./t01.txt') as f:
    print(f.readlines())



