# -*- coding: utf-8 -*-
# ********* RADIATION RISK ********* #
# @Time         : 18:23 2022/1/5
# @Author       : Chris
# @Description  :
from src.currency import fetch_exchange_rates

rates = fetch_exchange_rates()
print(rates)


import convert

data = [
        ('1RMB USD', )
    ]
c = convert.Converter(None)
for t in data:
    i = c.parse(t[0])
    res = c.convert(i)
    print(res)