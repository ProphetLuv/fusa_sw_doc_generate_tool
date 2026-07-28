#include "sensor.h"
static int g_raw;
void sensor_init(void){ g_raw = 0; }
int sensor_read(void){ return g_raw; }
void sensor_set(int v){ g_raw = v; }
