from q1.config import DELTA_H, ETA_C, ETA_D, P_MAX_KW, T

C_MAX = P_MAX_KW * DELTA_H
D_MAX = P_MAX_KW * DELTA_H

__all__ = ["C_MAX", "D_MAX", "DELTA_H", "ETA_C", "ETA_D", "T"]
