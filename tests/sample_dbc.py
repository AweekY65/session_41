"""Shared in-memory DBC text used across the test modules."""

DBC = r'''VERSION ""

NS_ :

BS_:

BU_: ECU1 ECU2

BO_ 100 EngineData: 8 ECU1
 SG_ RPM : 7|16@0+ (0.25,0) [0|16383.75] "rpm" ECU2
 SG_ Temp : 23|8@1- (1,-40) [-40|87] "degC" ECU2
 SG_ Flags : 32|4@1+ (1,0) [0|15] "" ECU2
 SG_ Throttle : 40|12@1+ (0.1,0) [0|409.5] "%" ECU2

BO_ 101 CrossByte: 8 ECU1
 SG_ IntelCross : 4|12@1+ (1,0) [0|4095] "" ECU2
 SG_ MotoCross : 27|12@0+ (1,0) [0|4095] "" ECU2
 SG_ SignedMoto : 47|16@0- (0.5,-10) [-16394|16373.5] "kW" ECU2

BO_ 200 MuxMsg: 8 ECU1
 SG_ Mode M : 7|4@0+ (1,0) [0|15] "" ECU2
 SG_ ModeA m0 : 15|16@0+ (1,0) [0|65535] "" ECU2
 SG_ ModeB m1 : 15|8@0- (1,0) [-128|127] "" ECU2
 SG_ ModeB2 m1 : 23|8@0+ (1,0) [0|255] "" ECU2
'''

DBC_SHORT = r'''VERSION ""

BO_ 256 Basic: 4 ECU1
 SG_ LE16 : 0|16@1- (2,100) [-131070|131170] "V" ECU2
 SG_ BES8 : 23|8@0- (1,-50) [-178|77] "C" ECU2
 SG_ BEU8 : 31|8@0+ (1,0) [0|255] "" ECU2
'''
