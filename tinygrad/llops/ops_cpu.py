import numpy as np
from tinygrad.helpers import get_conv_args
from tinygrad.ops import UnaryOps, BinaryOps, ReduceOps, MovementOps, ProcessingOps

class CPUBuffer(np.ndarray):
  def __new__(cls, shape, dtype=np.float32): return np.zeros(shape, dtype=dtype).view(CPUBuffer)
  def relu(x): return np.maximum(x, 0)
  def exp(x): return np.exp(x)
  def log(x): return np.log(x)
  def sign(x): return np.sign(x)
  def flip(x, axis): return np.flip(x, axis)
  def amax(x, *args, **kwargs): return np.amax(x, *args, **kwargs)
  def permute(x, order): return x.transpose(order)
  def custompad(x, padding): return np.pad(x, padding)
  def expand(x, new_shape): return np.broadcast_to(x, new_shape)

  @staticmethod
  def fromCPU(x): return x
  def toCPU(x): return x

def unary_op(op, x, ret):
  if op == UnaryOps.RELU: ret[:] = x.relu()
  elif op == UnaryOps.EXP: ret[:] = x.exp()
  elif op == UnaryOps.LOG: ret[:] = x.log()
  elif op == UnaryOps.NEG: ret[:] = -x
  elif op == UnaryOps.SIGN: ret[:] = x.sign()
  else: raise Exception(f"{op} isn't supported")

def binary_op(op, x, y, ret):
  if op == BinaryOps.ADD: ret[:] = x+y
  elif op == BinaryOps.SUB: ret[:] = x-y
  elif op == BinaryOps.MUL: ret[:] = x*y
  elif op == BinaryOps.DIV: ret[:] = y/x
  elif op == BinaryOps.POW: ret[:] = x**y
  elif op == BinaryOps.CMPEQ: ret[:] = 1.0*(x==y)
  else: raise Exception(f"{op} isn't supported")

def reduce_op(op, inp, ret):
  if inp.shape == ret.shape:   # this is just a copy, regardless of the reduce op
    ret[:] = inp
  else:
    if ret.shape == (1,):      # full reduce
      axis = tuple(range(len(inp.shape)))
    else:
      assert len(inp.shape) == len(ret.shape)
      axis = tuple([i for i,(a,b) in enumerate(zip(inp.shape, ret.shape)) if a != b])
    if op == ReduceOps.SUM: ret[:] = inp.sum(axis, keepdims=True)
    elif op == ReduceOps.MAX: ret[:] = inp.amax(axis, keepdims=True)
    else: raise Exception(f"{op} isn't supported")

def movement_op(op, x, ret, arg=None):
  if op == MovementOps.RESHAPE: ret[:] = x.reshape(arg)
  elif op == MovementOps.PERMUTE: ret[:] = x.permute(arg)
  elif op == MovementOps.FLIP: ret[:] = x.flip(arg)
  elif op == MovementOps.SLICE:
    padding = [(max(0, -p[0]), max(0, p[1]-x.shape[i])) for i,p in enumerate(arg)]
    x = x.custompad(padding)
    slicee = [(p[0] + padding[i][0], p[1] + padding[i][0]) for i,p in enumerate(arg)]
    ret[:] = x[tuple([slice(x[0], x[1], None) for x in slicee])]
  elif op == MovementOps.EXPAND: ret[:] = x.expand(arg)
  else: raise Exception(f"{op} isn't supported")

def get_tx(x, C):
  gx = x.reshape(C.bs,C.groups,C.cin,x.shape[2],x.shape[3])
  return np.lib.stride_tricks.as_strided(gx,
    shape=(C.bs, C.groups, C.cin, C.oy, C.ox, C.H, C.W),
    strides=(*gx.strides[0:3], gx.strides[3]*C.ys, gx.strides[4]*C.xs, gx.strides[3]*C.dy, gx.strides[4]*C.dx),
    writeable=False,
  )

def conv(x,w,ret,C):
  if C.px > 0 or C.py > 0: x = np.pad(x, [(0,0), (0,0), (C.py, C.py), (C.px, C.px)])
  tx = get_tx(x, C)
  tw = w.reshape(C.groups, C.rcout, C.cin, C.H, C.W)
  tmp = np.zeros((C.bs,C.groups,C.oy,C.ox,C.rcout),dtype=x.dtype)
  for g in range(C.groups):
    #ijYXyx,kjyx -> iYXk ->ikYX
    tmp[:,g] += np.tensordot(tx[:,g], tw[g], ((1,4,5),(1,2,3)))
  ret[:] = np.moveaxis(tmp,4,2).reshape(C.bs, C.groups*C.rcout, C.oy, C.ox)

def processing_op(op,a,b,ret,C):
  if op == ProcessingOps.CONV: conv(a,b,ret,C)
