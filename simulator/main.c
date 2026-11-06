#include "dashboard.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define WIDTH 240
#define HEIGHT 280
static lv_color_t pixels[WIDTH*HEIGHT], buffer[WIDTH*20];
static void flush(lv_disp_drv_t *drv,const lv_area_t *area,lv_color_t *p) {
    for(int y=area->y1;y<=area->y2;y++) for(int x=area->x1;x<=area->x2;x++) {
        if(x>=0 && x<WIDTH && y>=0 && y<HEIGHT) pixels[y*WIDTH+x]=*p;
        p++;
    }
    lv_disp_flush_ready(drv);
}
static void save(const char *path) {
    FILE *f=fopen(path,"wb"); if(!f) {perror(path); exit(1);}
    fprintf(f,"P6\n%d %d\n255\n",WIDTH,HEIGHT);
    for(int i=0;i<WIDTH*HEIGHT;i++) { lv_color_t c=pixels[i]; unsigned char rgb[]={c.ch.red,c.ch.green,c.ch.blue}; fwrite(rgb,1,3,f); }
    fclose(f);
}
static void start_display(void) {
    lv_init(); static lv_disp_draw_buf_t draw; lv_disp_draw_buf_init(&draw,buffer,NULL,WIDTH*20);
    static lv_disp_drv_t drv; lv_disp_drv_init(&drv); drv.hor_res=WIDTH; drv.ver_res=HEIGHT; drv.flush_cb=flush; drv.draw_buf=&draw; lv_disp_drv_register(&drv);
    lv_scr_load(dashboard_create());
}
static void render_frame(void) {
    lv_tick_inc(50); lv_timer_handler();
}
static int live(void) {
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    start_display();
    char line[160], layer_name[40]; int battery_value, output, connected, profile_value, wpm_value;
    int ll, lb, lc, rl, rb, rc, modifiers, is_live;
    while(fgets(line,sizeof line,stdin)) {
        if(sscanf(line,"%39s %d %d %d %d %d %d %d %d %d %d %d %d %d",layer_name,&battery_value,&output,&connected,&profile_value,&wpm_value,&ll,&lb,&lc,&rl,&rb,&rc,&modifiers,&is_live)!=14) continue;
        dashboard_state_t s={.layer=!strcmp(layer_name,"UNKNOWN") ? NULL : layer_name,.battery_percent=battery_value,.output=(dashboard_output_t)output,.connected=connected!=0,.profile=profile_value,.wpm=wpm_value,
            .left={(dashboard_link_t)ll,lb,(dashboard_charge_t)lc},.right={(dashboard_link_t)rl,rb,(dashboard_charge_t)rc},.modifiers=modifiers,.simulator_source=is_live ? 2 : 1};
        dashboard_update(&s); render_frame();
        for(int i=0;i<WIDTH*HEIGHT;i++) {
            lv_color_t c=pixels[i]; unsigned char rgb[]={c.ch.red,c.ch.green,c.ch.blue};
            if(fwrite(rgb,1,3,stdout)!=3) return 1;
        }
        if(fflush(stdout)!=0) return 1;
    }
    return 0;
}
int main(int argc,char **argv) {
    if(argc>1 && !strcmp(argv[1],"--live")) return live();
    const char *preset=argc>1?argv[1]:"normal", *path=argc>2?argv[2]:"dashboard.ppm";
    int ms=argc>3?atoi(argv[3]):250;
    dashboard_state_t s={"BASE",87,DASH_BLE,true,1,42};
    if(!strcmp(preset,"low")) s=(dashboard_state_t){"NAVIGATION",8,DASH_BLE,false,3,4};
    else if(!strcmp(preset,"usb")) s=(dashboard_state_t){"SYMBOLS",66,DASH_USB,true,2,120};
    else if(!strcmp(preset,"unavailable")) s=(dashboard_state_t){NULL,-1,DASH_UNAVAILABLE,false,-1,-1};
    else if(strcmp(preset,"normal") && strcmp(preset,"transition")) {fprintf(stderr,"Presets: normal low usb unavailable transition\n"); return 2;}
    if(strcmp(preset,"unavailable")) {
        s.left=(dashboard_half_t){DASH_LINK_ONLINE,82,DASH_CHARGE_UNKNOWN};
        s.right=(dashboard_half_t){DASH_LINK_ONLINE,67,DASH_CHARGE_YES};
    } else { s.left.battery_percent=-1; s.right.battery_percent=-1; }
    if(!strcmp(preset,"low")) {
        s.left=(dashboard_half_t){DASH_LINK_ONLINE,8,DASH_CHARGE_NO};
        s.right=(dashboard_half_t){DASH_LINK_OFFLINE,-1,DASH_CHARGE_UNKNOWN};
    }
    start_display(); dashboard_update(&s);
    for(int i=0;i<ms;i+=5) {
        if(!strcmp(preset,"transition") && i==((ms/10)*5)) {
            s=(dashboard_state_t){.layer="NAVIGATION",.battery_percent=8,.output=DASH_BLE,.connected=false,.profile=3,.wpm=4,
                .left={DASH_LINK_ONLINE,8,DASH_CHARGE_NO},.right={DASH_LINK_OFFLINE,-1,DASH_CHARGE_UNKNOWN}}; dashboard_update(&s);
        }
        lv_tick_inc(5);lv_timer_handler();
    }
    save(path); return 0;
}
