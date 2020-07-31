#ifndef __CCS811_SENSE_H__
#define __CCS811_SENSE_H__


typedef struct _env_values {
    unsigned int co2;
    unsigned int tvoc;
    bool valid;
} env_values_t;


void ccs811_init();
int get_env_sample(env_values_t &env_values);


#endif /* __CCS811_SENSE_H__ */

