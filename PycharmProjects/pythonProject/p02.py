from typing import Iterable, Iterator, Generator


class ContainerIterator:
    def __init__(self, container):
        self.container = container
        self.cursor = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.cursor < len(self.container.iterable):
            item = self.container.iterable[self.cursor]
            self.cursor += 1
            return item

        raise StopIteration


class Container:
    def __init__(self, iterable):
        self.iterable = iterable

    def __iter__(self):
        return ContainerIterator(self)

cont = Container([1, 2, 3, 4, 5])
cont_iterator = cont.__iter__()


for i in cont.__iter__():
    print(i)

for j in cont.__iter__():
    print(j)

print(cont_iterator.__next__())
