import math
import re

# cw - canvas width
# ch - canvas height
# ow - canvas object width
# oh - canvas object height
# ew - element width
# eh - element height

# percent(90)

# rel(0.9, "object.x")

REL_NAME_PATTERN = r"[a-zA-Z0-9_\-]+"
REL_QUALIFIER_PATTERN = r"[a-zA-Z0-9_\-:]+"
REL_ATTRIBUTE_PATTERN = REL_NAME_PATTERN

REL_NAME_RE = re.compile(f"(?P<name>{REL_NAME_PATTERN})(?:\\[(?P<qualifier>{REL_QUALIFIER_PATTERN})\\])?\\.(?P<attribute>{REL_ATTRIBUTE_PATTERN})")
ELEMENT_NAME_RE = re.compile(REL_NAME_PATTERN)

#JS re: /^(?<name>[a-zA-Z0-9_\-]+)(?:\[(?<qualifier>[a-zA-Z0-9_\-:]+)\])?\.(?<attribute>[a-zA-Z0-9_\-]+)$/

class _relmath:
    def __iadd__(self, other):
        return self.__add__(other)

    def __isub__(self, other):
        return self.__sub__(other)

    def __imul__(self, other):
        return self.__mul__(other)

    def __itruediv__(self, other):
        return self.__truediv__(other)

    def __floordiv__(self, other):
        return NotImplemented

    def __ifloordiv__(self, other):
        return self.__floordiv__(other)


class Rel(_relmath):
    __slots__ = "weight", "name"

    def __init__(self, weight:float, name:str):
        self.weight = weight
        self.name = name

    def __getstate__(self):
        return dict(
            weight=self.weight,
            name=self.name
        )
    
    def __setstate__(self, d:dict[str]):
        self.weight = float(d["weight"])
        self.name = str(d["name"])

    def __eq__(self, value):
        if isinstance(value, Rel):
            return self.weight == value.weight and self.name == value.name
        return super().__eq__(value)
    
    def __ne__(self, value):
        if isinstance(value, Rel):
            return self.weight != value.weight or self.name != value.name
        return super().__ne__(value)
    
    def _compare(self, value):
        if isinstance(value, Rel):
            if self.name == value.name:
                return self.weight == value.weight
            else:
                raise TypeError(f"can only compare relative values of the same type, got: {repr(self.name)}, {repr(value.name)}")
        return super().__eq__(value)
    
    def __gt__(self, other):
        return NotImplemented
    
    def __ge__(self, other):
        return NotImplemented
    
    def __lt__(self, other):
        return NotImplemented
    
    def __le__(self, other):
        return NotImplemented
    
    #c + a + b
    def __add__(self, other:"Rel|RelPromise|int|float"):
        if isinstance(other, Rel):
            if self.name == other.name:
                return Rel(self.weight + other.weight, self.name)
            else:
                return RelPromise("+", None, self, other)
        elif isinstance(other, RelPromise):
            if other.op == "+":
                return RelPromise(other.op, other.c, self, *other.rels)
            else:
                return RelPromise("+", None, self, other)
        elif other == 0:
            return self
        elif isinstance(other, (float, int)):
            return RelPromise("+", other, self)
        return NotImplemented
    
    #c - a - b
    #a - b
    def __sub__(self, other):
        if isinstance(other, Rel):
            if self.name == other.name:
                return Rel(self.weight - other.weight, self.name)
            else:
                return RelPromise("-", None, self, other)
        elif isinstance(other, RelPromise): #s - (c - a - b) = s - c + a + b = (-c) + s + a + b
            if other.op == "-":
                return RelPromise("+", -other.c, self, *other.rels)
            else:
                return RelPromise("-", None, self, other)
        elif other == 0:
            return self
        elif isinstance(other, (float, int)):
            return RelPromise("+", -other, self)
        return NotImplemented
    
    #c * a * b
    def __mul__(self, other):
        if isinstance(other, Rel):
            if self.name == other.name:
                return Rel(self.weight * other.weight, self.name)
            else:
                return RelPromise("*", None, self, other)
        elif isinstance(other, RelPromise):
            if other.op == "*":
                return RelPromise(other.op, other.c, self, *other.rels)
            else:
                return RelPromise("*", None, self, other)
        elif other == 1:
            return self
        elif isinstance(other, (float, int)):
            return RelPromise("*", other, self)
        return NotImplemented
    
    # c / a / b
    def __truediv__(self, other):
        if isinstance(other, Rel):
            if self.name == other.name:
                return Rel(self.weight / other.weight, self.name)
            else:
                return RelPromise("/", None, self, other)
        elif isinstance(other, RelPromise): # s / (c / a / b) = s * a * b / c = 1/c * s * a * b
            if other.op == "/":
                return RelPromise("*", 1/other.c, self, *other.rels)
            else:
                return RelPromise("/", None, self, other)
        elif other == 1:
            return self
        elif isinstance(other, (float, int)):
            return RelPromise("*", 1/other, self)
        return NotImplemented
    
    def __radd__(self, other):
        if isinstance(other, (int, float)):
            return RelPromise("+", other, self)
        return NotImplemented
    
    def __rsub__(self, other):
        if isinstance(other, (int, float)):
            return RelPromise("-", other, self)
        return NotImplemented

    def __rmul__(self, other):
        if isinstance(other, (int, float)):
            return RelPromise("*", other, self)
        return NotImplemented
    
    def __rtruediv__(self, other):
        if isinstance(other, (int, float)):
            return RelPromise("/", other, self)
        return NotImplemented

    def __pos__(self):
        return Rel(+self.weight, self.name)
    
    def __neg__(self):
        return Rel(-self.weight, self.name)
        

class RelPromise(_relmath):
    __slots__ = "op", "rels", "c"

    def __init__(self, op:str, c:int|float|None=None, *rels:"Rel|RelPromise"):
        self.op = op
        self.rels = list(rels)
        self.c = c

    def __eq__(self, value):
        if isinstance(value, RelPromise):
            return self.op == value.op and self.rels == self.rels
        return super().__eq__(value)
    
    def __ne__(self, value):
        if isinstance(value, RelPromise):
            return self.op != value.op or self.rels != value.rels
        return super().__ne__(value)
    
    def __gt__(self, other):
        return NotImplemented
    
    def __ge__(self, other):
        return NotImplemented
    
    def __lt__(self, other):
        return NotImplemented
    
    def __le__(self, other):
        return NotImplemented
    
    def __add__(self, other):
        if isinstance(other, RelPromise):
            if self.op == "+": 
                if self.op == other.op: # (c + a + b) + (k + x + y) = (c + k) + a + b + x + y
                    return RelPromise(self.op, (self.c or 0) + (other.c or 0), *self.rels, *other.rels)
                else: # (c + a + b) + (k ? x ? y)
                    return RelPromise(self.op, self.c, *self.rels, other)
            elif other.op == "+": #(c ? a ? b) + (k + x + y) = k + (c ? a ? b) + x + y
                return RelPromise(other.op, other.c, self, *other.rels)
            else:
                return RelPromise("+", None, self, other)
        elif isinstance(other, Rel):
            if self.op == "+":
                return RelPromise(self.op, self.c, *self.rels, other)
            else:
                return RelPromise("+", None, self, other)
        elif other == 0:
            return self
        elif isinstance(other, (float, int)):
            if self.op == "+":
                return RelPromise("+", other + (self.c or 0), *self.rels)
            else:
                return RelPromise("+", other, self)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, RelPromise):
            if self.op == "-":
                if self.op == other.op:
                    #case1: (c - a - b) - (k - x - y) = c - a - b - k + x + y = ((c - k) - a - b) + x + y
                    #case2:(a - b) - (k - x - y) = a - b - k + x + y = (-k - b) + a + x + y
                    #case3:(c - a - b) - (x - y) = c - a - b - x + y = (c - a - b - x) + y
                    #case4:(a - b) - (x - y) = a - b - x + y = (a - b - x) + y
                    if self.c is None:
                        if other.c is None: #case4
                            f, *o = other.rels
                            return RelPromise("+", None, RelPromise("-", None, *self.rels, f), *o)
                        else: #case2
                            f, *o = self.rels
                            return RelPromise("+", None, RelPromise("-", -other.c, *o), f, *other.rels)
                    elif other.c is None: #case3
                        f, *o = other.rels
                        return RelPromise("+", None, RelPromise("-", self.c, *self.rels, f), *o)
                    else: #case1
                        return RelPromise("+", None, RelPromise("-", self.c - other.c, *self.rels), *other.rels)
                else: # (c - a - b) - (k ? x ? y)
                    return RelPromise("-", self.c, *self.rels, other)
            elif other.op == "-":
                if other.c is None: #(c ? a ? b) - (x - y) = (c ? a ? b) + (-x) + y
                    f, *o = other.rels
                    return RelPromise("+", None, self, -f, *o)
                else: #(c ? a ? b) - (k - x - y) = -k + (c ? a ? b) + x + y
                    return RelPromise("+", -other.c, self, *other.rels)
            else:
                return RelPromise("-", None, self, other)
        elif isinstance(other, Rel):
            if self.op == "-":
                return RelPromise(self.op, self.c, *self.rels, other)
            else:
                return RelPromise("-", None, self, other)
        elif other == 0:
            return self
        elif isinstance(other, (float, int)):
            if self.c is None: #(a - b) - s = a - b - s = (-s) + (a - b)
                return RelPromise("+", -other, RelPromise("-", None, *self.rels))
            else: # (c - a - b) - s = c - a - b - s = (c-s) - a - b
                return RelPromise("-", self.c - other, *self.rels)
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, RelPromise):
            if self.op == "*": 
                if self.op == other.op: # (c * a * b) * (k * x * y) = (c * k) * a * b * x * y
                    return RelPromise(self.op, (1 if self.c is None else self.c) * (1 if other.c is None else other.c), *self.rels, *other.rels)
                else: # (c * a * b) * (k ? x ? y)
                    return RelPromise(self.op, self.c, *self.rels, other)
            elif other.op == "*": #(c ? a ? b) * (k * x * y) = k * (c ? a ? b) * x * y
                return RelPromise(other.op, other.c, self, *other.rels)
            else:
                return RelPromise("*", None, self, other)
        elif isinstance(other, Rel):
            if self.op == "*":
                return RelPromise(self.op, self.c, *self.rels, other)
            else:
                return RelPromise("*", None, self, other)
        elif other == 1:
            return self
        elif isinstance(other, (float, int)):
            if self.op == "*":
                return RelPromise("*", (1 if self.c is None else self.c) * other, *self.rels)
            else:
                return RelPromise("*", other, self)
        return NotImplemented

    def __truediv__(self, other):
        if isinstance(other, RelPromise):
            if self.op == "/":
                if self.op == other.op: #(c / a / b) / (k / x / y) = (c/ab) / (k/xy) = (c/k) * x * y / a / b
                    return RelPromise("*", self.c/other.c, *other.rels, RelPromise("/", 1, *self.rels))
                else: #(c / a / b) / (k ? x ? y) = c / a / b / (k ? x ? y)
                    return RelPromise("/", self.c, *self.rels, other)
            elif other.op == "/": #(c ? a ? b) / (k / x / y) = (1/k) * (c ? a ? b) * x * y
                return RelPromise("*", 1/other.c, self, *other.rels)
            else:
                return RelPromise("*", None, self, RelPromise("/", 1, other))
        elif isinstance(other, Rel):
            if self.op == "/": # (c / a / b) / other = c / a / b / other
                return RelPromise(self.op, self.c, *self.rels, other)
            else: # (c ? a ? b) / other = (c ? a ? b) * (1/other)
                return RelPromise("*", None, self, RelPromise("/", 1, other))
        elif other == 1:
            return self
        elif isinstance(other, (float, int)):
            if self.op == "*":
                return RelPromise("*", 1/other, *self.rels)
            else:
                return RelPromise("*", 1/other, self)
        return NotImplemented

    def __radd__(self, other):
        if isinstance(other, (int, float)):
            if self.op == "+":
                return RelPromise("+", other + (self.c or 0), *self.rels)
            else:
                return RelPromise("+", other, self)
        return NotImplemented

    def __rsub__(self, other):
        if isinstance(other, (int, float)):
            if self.op == "-": #k - (c - a - b) = (k - c) + a + b
                return RelPromise("+", other - (self.c or 0), *self.rels)
            else:
                return RelPromise("-", other, self)
        return NotImplemented

    def __rmul__(self, other):
        if isinstance(other, (int, float)):
            if self.op == "*":
                return RelPromise("*", other * (self.c or 1), *self.rels)
            else:
                return RelPromise("*", other, self)
        return NotImplemented

    def __rtruediv__(self, other):
        if isinstance(other, (int, float)):
            if self.op == "/": # k / (c / a / b) = (k / c) * a * b
                return RelPromise("/", other / (self.c or 1), *self.rels)
            else:
                return RelPromise("/", other, self)
        return NotImplemented

    def __pos__(self):
        return RelPromise(self.op, self.c, *self.rels)

    def __neg__(self):
        return RelPromise(self.op, None if self.c is None else -self.c, *(-rel for rel in self.rels))

    def __getstate__(self):
        return dict(
            op=self.op,
            rels=[(0 if isinstance(r, Rel) else 1, r.__getstate__()) for r in self.rels],
            c=self.c
        )
    
    def __setstate__(self, d:dict[str]):
        self.op = str(d["op"])
        rels = []
        dv = d.get("rels", None)
        if dv:
            for x, v in dv:
                if x:
                    recon = RelPromise.__new__(RelPromise)
                else:
                    recon = Rel.__new__(Rel)
                recon.__setstate__(v)
                rels.append(recon)
        self.rels = rels
        self.c = None if (c := d.get("c", None)) is None else c if isinstance(c, (float, int)) else float(c)