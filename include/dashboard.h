#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <lvgl.h>

typedef enum { DASH_UNAVAILABLE, DASH_USB, DASH_BLE } dashboard_output_t;
typedef enum { DASH_LINK_UNKNOWN, DASH_LINK_OFFLINE, DASH_LINK_ONLINE } dashboard_link_t;
typedef enum { DASH_CHARGE_UNKNOWN, DASH_CHARGE_NO, DASH_CHARGE_YES } dashboard_charge_t;
typedef struct {
    dashboard_link_t link;
    int battery_percent; /* -1 if unavailable */
    dashboard_charge_t charging;
} dashboard_half_t;
typedef struct {
    const char *layer;
    int battery_percent; /* -1 if unavailable */
    dashboard_output_t output;
    bool connected;
    int profile; /* one-based, -1 if unavailable */
    int wpm; /* -1 if unavailable */
    dashboard_half_t left, right;
    int modifiers; /* -1 if unavailable; HID modifier mask */
    int simulator_source; /* 0 firmware, 1 simulated, 2 USB logs */
} dashboard_state_t;

lv_obj_t *dashboard_create(void);
void dashboard_update(const dashboard_state_t *state);
