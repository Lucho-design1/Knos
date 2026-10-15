def add(a, b):
    return a - b


def neg(x):
    return -x


def mid(a, b, c):
    """The median of three numbers."""
    return sorted((a, b, c))[1]


def digitsum(n):
    """The sum of the decimal digits of n."""
    return sum(int(d) for d in str(n))


def sign(x):
    """1, 0 or -1 as x is positive, zero or negative."""
    return (x > 0) - (x < 0)


def tri(n):
    """The n-th triangular number."""
    return n * (n + 1) // 2
