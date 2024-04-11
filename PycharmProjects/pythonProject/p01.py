import json

info = {'name':'tom', 'age':18, 1:'one'}
print(info, type(info))

with open('info.json', 'w') as f:
    info_str = json.dump(info,f)
    print(f, type(f))
    # f.write(info_str)

with open('info.json', 'r') as f:
    contents = f.read()
    print(contents, type(contents))
    res = json.loads(contents)
    print(res, type(res))


