# can_dbc — 本地 CAN DBC 信号编码/解码工具

一个**纯本地、无硬件依赖、无网络访问**的 CAN Bus DBC（Vector `.dbc`）解析与
信号编解码工具。所有 DBC 定义、CAN frame、解析状态和测试数据都只存在于本地
文件或内存中：

- 不连接真实 CAN 总线 / 车辆 / SocketCAN (`can0`、`python-can` 等)
- 不连接云平台或任何外部服务
- 核心 DBC 解析、Intel/Motorola 位布局、signed/unsigned、缩放偏移和
  multiplexing 全部在 `can_dbc/` 包内手写实现，**零第三方运行时依赖**
- 仅在测试中可选使用 [`cantools`](https://pypi.org/project/cantools/) 作为
  第三方对照（test oracle）；未安装时该测试自动跳过

## 目录结构

```
can_dbc/
  __init__.py     公共 API 导出
  errors.py       异常类型（解析/重叠/越界/DLC/编解码错误）
  layout.py       DBC 位编号 -> 线序 bit 的 Intel/Motorola 布局数学
  model.py        Signal / Message / Database 数据模型与校验
  parser.py       手写 DBC 词法/语法解析
  codec.py        raw 与 physical 两级 encode/decode
  __main__.py     命令行界面 (decode / encode / show)
examples/
  example.dbc     示例 DBC（含大小端、signed、跨字节、multiplexed）
tests/            自动化测试（可独立运行，也可被 pytest 收集）
run_tests.py      一键运行全部测试
```

## 运行环境

- Python 3.9+（标准库即可运行；开发验证使用 3.12）
- 无需 CAN 硬件、GUI 或网络

## 快速开始

### 命令行

```bash
# 查看 DBC 中解析出的 message/signal
python -m can_dbc show examples/example.dbc
python -m can_dbc show examples/example.dbc 0x64

# 解码十六进制 CAN payload（输出 frame 及各信号物理值与单位）
python -m can_dbc decode examples/example.dbc 0x64 2ee0802005f40100
# frame 0x64 [8] 2ee0802005f40100
#   RPM = 3000.0 rpm
#   Temp = 25.0 degC
#   Flags = 5.0
#   Throttle = 50.0 %

# 编码物理值为十六进制 payload
python -m can_dbc encode examples/example.dbc 0x64 \
    RPM=3000 Temp=25 Flags=5 Throttle=50
# frame 0x64 [8] 2ee0802005f40100

# multiplexed message：选择 Mode=1 分支并编码该分支信号
python -m can_dbc encode examples/example.dbc 200 Mode=1 ModeB=-5 ModeB2=200
# frame 0xC8 [8] 10fbc80000000000

# 超范围输入返回非零退出码和明确诊断
python -m can_dbc encode examples/example.dbc 0x64 RPM=99999
# error: signal 'RPM': physical value 99999 maps to raw 399996, outside
#        [0, 65535] (physical range [0, 16383.75])
```

### Python API

```python
from can_dbc import load_file, encode, decode, encode_raw, decode_raw

db = load_file("examples/example.dbc")
msg = db.by_id(0x64)

payload = encode({"RPM": 3000.0, "Temp": 25.0, "Flags": 5,
                  "Throttle": 50.0}, msg)
print(payload.hex())          # 2ee0802005f40100

values = decode(payload, msg)
# {'RPM': 3000.0, 'Temp': 25.0, 'Flags': 5.0, 'Throttle': 50.0}

# 也可以直接操作 raw 整数（不做缩放）
raw = encode_raw({"RPM": 12000}, msg)
decode_raw(payload, msg)      # {'RPM': 12000, ...}

# 也支持按 Database + frame_id 调用
decode(payload, db, frame_id=0x64)
```

## DBC 支持范围

| 特性 | 支持情况 |
| --- | --- |
| `VERSION` / `NS_` / `BS_` / `BU_` | 解析并接受 |
| `BO_ <id> <name>: <dlc> <sender>` | 完整解析（标准 11-bit 与扩展 29-bit id，含 `0x80000000` 标志） |
| `SG_ <name> : <start>\|<len>@<byte_order><sign>` | 完整解析 |
| factor `(scale,offset)`、range `[min\|max]`、`"unit"`、接收节点 | 完整解析 |
| Intel little-endian (`@1`) | ✅ 含跨字节字段 |
| Motorola big-endian (`@0`) | ✅ 含跨字节（“之”字形回绕）字段 |
| unsigned (`+`) / signed (`-`) | ✅ 二进制补码 |
| 基础 multiplexing：`SG_ X M :` 开关 + `SG_ Y m<value> :` 分支 | ✅ |
| 扩展 multiplexing 语法 `m<value>,<switch-name>` | 解析（依赖关系建模） |
| `CM_` / `BA_` / `VAL_` / `BA_DEF_` 等其它 DBC 段 | 接受并跳过（不参与编解码） |
| line comment `// ...` | 正确处理（尊重字符串内容） |
| choice tables (`VAL_`)、float 信号 (`SIG_VALTYPE_`) | 不作为本工具的编解码目标（按普通数值接受定义） |

## Bit 编号规则

CAN payload 按字节在线上传输。本工具内部使用统一的**线序 bit 编号**：

```
wire_bit = byte_index * 8 + bit_index_in_byte        (bit_index 从该字节 LSB=0 起)

字节0: wire  7  6  5  4  3  2  1  0
字节1: wire 15 14 13 12 11 10  9  8
...
```

DBC 里 `SG_` 的 start bit 使用 Vector/CANdb 编辑器的**锯齿（sawtooth）
编号**，其数值恰好与线序编号一致，但两种字节序赋予它的含义不同：

- **Intel (`@1`, little-endian)**：start bit 是信号的 **LSB**，后续 bit 沿
  线序递增排列，信号跨越字节边界时无缝进入下一字节高位。
  例：`4|12@1` 占用线序 bit `4..15`（横跨字节 0/1）。

- **Motorola (`@0`, big-endian)**：start bit 是信号的 **MSB**（位于信号的
  最低编号字节）。从 MSB 起按锯齿编号逐 bit 向下走；走到一个字节的 LSB 后，
  下一位回绕到**下一个字节**的 MSB（锯齿编号 +15，而不是进入前一个字节）。
  经典跨字节例子：`11|12@0` 高 4 位在线序 bit `11..8`，低 8 位在
  `23..16`，即 payload `00 01 23 ..` 解码为 `0x123`。

该规则与 `cantools` 逐 bit 一致（见 `tests/test_cantools_xcheck.py` 的
随机对照，及 `tests/test_layout.py` 的固定向量）。

信号的位布局在解析时一次性计算为“MSB 在前的线序 bit 列表”，因此
pack/unpack 与字节序无关，只是一次逐 bit 读写。

## 转换公式

```
physical = raw * scale + offset          # 解码
raw      = round((physical - offset) / scale)   # 编码（四舍五入，与 cantools 一致）
```

- unsigned：`raw ∈ [0, 2^len − 1]`
- signed（二进制补码）：`raw ∈ [−2^(len−1), 2^(len−1) − 1]`

编码时：

- raw 超出信号可表示范围 → `EncodeError`，错误信息同时给出 raw 范围与
  对应的 physical 范围（正确处理负 scale 的反向区间）。
- physical 不能精确映射到整数 raw（如 scale=0.25 时传入 3000.1）→
  默认 strict 模式抛 `EncodeError`；`encode(..., strict=False)` 时量化到
  最近 raw 值。
- multiplexed 信号若与给定的 multiplexer 开关值不匹配 → `EncodeError`。

## Multiplexing 语义

解码时先读取所有 multiplexer 开关（`M`），随后只解码依赖条件
`(开关名 == m值)` 成立的分支信号；其它分支即使在相同 bit 上留有旧数据也
不会出现在结果中。编码时只需要给出目标分支的信号；跨分支的 bit 重叠是
合法的，同一分支内 / 常在场信号之间的重叠会在解析期报
`SignalOverlapError`。

## 诊断能力（解析期 / 运行期）

| 场景 | 异常类型 |
| --- | --- |
| 重复 message id（含标准/扩展 id 冲突） | `DuplicateMessageIdError` |
| 信号 bit 重叠（同一 multiplexer 分支或常在场内） | `SignalOverlapError` |
| start/length 使信号超出 DLC（两种字节序均检查） | `BitOutOfBoundsError` |
| 无法识别的 DBC token、截断/畸形的 `BO_`/`SG_`、非法 DLC、长度 0 等 | `DbcParseError` |
| payload 长度与 message DLC 不符 | `DlcError` |
| 编码超范围 / 非整数值 / 未知信号 / mux 分支冲突 | `EncodeError` |
| 数据库中无对应 frame id、payload 非 bytes | `DecodeError` |

所有异常都继承自 `can_dbc.DbcError`。

## 运行测试

无需 CAN 硬件或 GUI，全部在终端完成，测试输出包含十六进制 frame 与每条
断言的 PASS/FAIL：

```bash
# 方式一：自带运行器（无第三方依赖也能跑，只是没有 cantools 对照）
python run_tests.py

# 方式二：pytest
python -m pytest -v tests/

# 单独运行某个套件
python tests/test_layout.py
python tests/test_encode.py
python tests/test_cantools_xcheck.py   # 无 cantools 时自动跳过
```

测试覆盖：

1. **位布局**：Intel/Motorola、跨字节、回绕、越界诊断（固定向量）
2. **解码**：大小端、signed/unsigned、跨字节、scale/offset、cantools 向量
3. **编码 + round-trip**：已知十六进制向量、边界值、raw 接口、超范围/
   不可表示值/未知信号错误、non-strict 量化
4. **multiplexing**：分支选择、旧字节隔离、分支冲突、跨/同分支重叠、
   缺少开关
5. **非法 DBC / 诊断**：重复 id、重叠、越界 bit、损坏文本、错误 DLC、
   NaN/inf 输入
6. **cantools 随机对照**：对三个 message 各 25 帧随机 encode、25 帧随机
   decode（共 150 帧），逐字节/逐信号与 cantools 比对

所有测试在本机验证通过（`ALL 6 TEST SUITES PASSED`）。
