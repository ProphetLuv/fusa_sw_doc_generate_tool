#include "brake.h"
static int g_pressure;
void brake_init(void){ g_pressure = 0; }
int brake_apply(int level){ if(level<0) return -1; g_pressure = level; return g_pressure; }
