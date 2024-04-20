import math  # 可选
import numpy as np # 可选
import latexify
from math import factorial
from sympy import symbols, Function, diff, factorial, latex

# 定义符号变量和函数
x, a = symbols('x a')
f = Function('f')
@latexify.function
def taylor_series_expansion(f, a, n):
    # 构建泰勒展开式
    return sum([f(a)**k / factorial(k) * (x - a)**k for k in range(n+1)])

# 使用示例

# 使用示例
# 假设我们要展开 e^x 在 x = 0 的泰勒展开式到第5阶
# f = x.exp()
# latex_expr = taylor_series_latex(f, 0, 5)
print(taylor_series_expansion)
# print(latexify.get_latex(taylor_series_expansion))
