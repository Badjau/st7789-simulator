#include "dashboard.h"
#include <stdio.h>

static lv_obj_t *layer, *connection, *profile, *wpm, *dot, *modifiers, *layer_source, *wpm_source;
static lv_obj_t *half_link[2], *half_battery[2], *half_charge[2], *half_header[2], *host_header, *profile_header;
static const lv_color_t bg = LV_COLOR_MAKE(17, 21, 25);
static const lv_color_t card = LV_COLOR_MAKE(29, 35, 40);
static const lv_color_t white = LV_COLOR_MAKE(238, 241, 237);
static const lv_color_t muted = LV_COLOR_MAKE(150, 162, 162);
static const lv_color_t accent = LV_COLOR_MAKE(166, 199, 179);

static lv_obj_t *label(lv_obj_t *parent, const char *text, int x, int y, int width, const lv_font_t *font, lv_color_t color) {
    lv_obj_t *o = lv_label_create(parent);
    lv_obj_set_pos(o, x, y); lv_obj_set_width(o, width);
    lv_label_set_long_mode(o, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_font(o, font, 0); lv_obj_set_style_text_color(o, color, 0);
    lv_label_set_text(o, text); return o;
}
static lv_obj_t *panel(lv_obj_t *parent, int x, int y, int w, int h) {
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o); lv_obj_set_pos(o,x,y); lv_obj_set_size(o,w,h);
    lv_obj_set_style_bg_color(o,card,0); lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
    lv_obj_set_style_radius(o,8,0); lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE); return o;
}
lv_obj_t *dashboard_create(void) {
    lv_obj_t *s=lv_obj_create(NULL); lv_obj_clear_flag(s,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(s,bg,0); lv_obj_set_style_bg_opa(s,LV_OPA_COVER,0);
    label(s,"KEYBOARD",14,10,100,&lv_font_montserrat_12,muted);
    label(s,"STATUS",14,25,115,&lv_font_montserrat_20,white);
    wpm_source=label(s,"WPM EST",148,10,70,&lv_font_montserrat_12,muted);
    wpm=label(s,"N/A",148,26,65,&lv_font_montserrat_20,white);
    dot=lv_obj_create(s); lv_obj_remove_style_all(dot); lv_obj_set_pos(dot,218,15); lv_obj_set_size(dot,8,8);
    lv_obj_set_style_radius(dot,LV_RADIUS_CIRCLE,0); lv_obj_set_style_bg_opa(dot,LV_OPA_COVER,0);
    lv_obj_t *a=panel(s,12,54,216,50);
    layer_source=label(a,"LAYER SIM",10,6,100,&lv_font_montserrat_12,muted);
    modifiers=label(a,"MOD N/A",112,6,98,&lv_font_montserrat_12,muted);
    layer=label(a,"N/A",10,23,196,&lv_font_montserrat_20,white);
    for(int i=0;i<2;i++) {
        a=panel(s,12+i*112,112,104,98);
        half_header[i]=label(a,i==0 ? "LEFT" : "RIGHT",9,7,86,&lv_font_montserrat_12,muted);
        half_link[i]=label(a,"Unknown",9,24,88,&lv_font_montserrat_12,white);
        half_battery[i]=label(a,"N/A",9,43,86,&lv_font_montserrat_20,white);
        half_charge[i]=label(a,"Charge: N/A",9,75,88,&lv_font_montserrat_12,muted);
    }
    a=panel(s,12,218,216,50);
    host_header=label(a,"HOST",10,6,101,&lv_font_montserrat_12,muted);
    profile_header=label(a,"PROFILE",124,6,82,&lv_font_montserrat_12,muted);
    connection=label(a,"N/A",10,25,110,&lv_font_montserrat_14,white);
    profile=label(a,"N/A",124,25,82,&lv_font_montserrat_14,white);
    return s;
}
void dashboard_update(const dashboard_state_t *s) {
    char b[24];
    lv_label_set_text(layer,s->layer && *s->layer ? s->layer : "Unknown");
    lv_label_set_text(layer_source,s->simulator_source==2 ? "LAYER OBS" : s->simulator_source==1 ? "LAYER SIM" : "LAYER");
    lv_label_set_text(wpm_source,s->simulator_source==2 ? "WPM LIVE" : s->simulator_source==1 ? "WPM EST" : "WPM");
    if(s->modifiers < 0) lv_label_set_text(modifiers,"MOD N/A");
    else {
        snprintf(b,sizeof b,"%c %c %c %c", (s->modifiers & 0x01) ? 'C' : '-',
                 (s->modifiers & 0x02) ? 'S' : '-', (s->modifiers & 0x04) ? 'A' : '-',
                 (s->modifiers & 0x08) ? 'G' : '-');
        lv_label_set_text(modifiers,b);
    }
    if(s->wpm < 0) lv_label_set_text(wpm,"N/A");
    else { snprintf(b,sizeof b,"%d",s->wpm); lv_label_set_text(wpm,b); }
    lv_label_set_text(half_header[0],s->simulator_source ? "LEFT SIM" : "LEFT");
    lv_label_set_text(half_header[1],s->simulator_source ? "RIGHT SIM" : "RIGHT");
    lv_label_set_text(host_header,s->simulator_source ? "HOST SIM" : "HOST");
    lv_label_set_text(profile_header,s->simulator_source ? "BT SIM" : "PROFILE");
    const dashboard_half_t halves[2]={s->left,s->right};
    for(int i=0;i<2;i++) {
        const dashboard_half_t *h=&halves[i];
        lv_label_set_text(half_link[i],h->link==DASH_LINK_ONLINE ? "Connected" : h->link==DASH_LINK_OFFLINE ? "Disconnected" : "Unknown");
        if(h->link!=DASH_LINK_ONLINE || h->battery_percent<0) lv_label_set_text(half_battery[i],"N/A");
        else {snprintf(b,sizeof b,"%d%%",h->battery_percent); lv_label_set_text(half_battery[i],b);}
        lv_label_set_text(half_charge[i],h->link!=DASH_LINK_ONLINE || h->charging==DASH_CHARGE_UNKNOWN ? "Charge: N/A" : h->charging==DASH_CHARGE_YES ? "Charging" : "Not charging");
    }
    lv_label_set_text(connection,s->output==DASH_BLE ? (s->connected ? "BT connected" : "BT offline") : s->output==DASH_USB ? (s->connected ? "USB ready" : "USB offline") : "Unavailable");
    if(s->profile < 0) lv_label_set_text(profile,"N/A");
    else { snprintf(b,sizeof b,"BT %d",s->profile); lv_label_set_text(profile,b); }
    lv_obj_set_style_bg_color(dot,s->connected ? accent : muted,0);
}
