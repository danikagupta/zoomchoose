import streamlit as st
import json
import pandas as pd
import os
from datetime import datetime
from datetime import timedelta
from zoom_integration import get_schedules
import pytz

#
# All internal calculations are in UTC
# Convert to user-friendly timezones at IO
#

zoom_sessions={
'14FZQXqLRSODS33uQTVVaw':'AZ2',
'5uBBBmxkRs2ULd5cfs8Adw':'AZ5',
'atAAAIDOQYqcONrWd0oxxg':'AZ1',
'dZ6K_rnJTOO5S-jOUpXf3w':'AZ3',
'di6QjKDzTA-BsECJM-lqDA':'AZ7',
'j4IclWA4ScOUmP_grnbflg':'AZ4',
}

def create_df(s):
    dataset=json.loads(s)
    me=dataset['meetings']
    df_combined=pd.DataFrame()
    for ke,_ in me.items():
        upc=me[ke]['upcoming']
        ses=upc['sessions']
        #print(f"{ke} upc-ses: {ses}")
        df_new=pd.DataFrame(ses)
        if not df_new.empty:
            df_new['start_time'] = pd.to_datetime(df_new['start_time'])
            df_new['end_time'] = df_new['start_time']+pd.to_timedelta(df_new['duration'], unit='m')
            df_combined = pd.concat([df_combined, df_new], ignore_index=True)
    df_combined['host_id']=df_combined['host_id'].replace(zoom_sessions)
    df_combined['start_time'] = pd.to_datetime(df_combined['start_time'])
    df_combined['end_time'] = pd.to_datetime(df_combined['end_time'])
    #print(f"{ke} df: \n{df_combined.info()}")

    return df_combined

def find_closest_record_before(host_id, df_combined, date_time, duration):
  if not isinstance(date_time, pd.Timestamp):
    date_time = pd.to_datetime(date_time)
  if df_combined['end_time'].dtype.tz is not None:
    #date_time = date_time.tz_localize('UTC')  # or use tz_convert('UTC') if it already has a timezone
    date_time = date_time.tz_convert('UTC')  # or use tz_localize('UTC') if it does not has a timezone

  #st.write(f"Date time is {date_time} with type {type(date_time)}")
  #st.write(f"Start time type is {df_combined['start_time'].apply(type)}")
  #st.write(f"End time type is {df_combined['end_time'].apply(type)}")
  df_filtered = df_combined[(df_combined['end_time'] <= date_time) & (df_combined['host_id'] == host_id)]
  if df_filtered.empty:
    return 'N.A.',None,14400
  closest_record = df_filtered.loc[df_filtered['start_time'].idxmax()]
  closest_end_time = closest_record['start_time'] + pd.Timedelta(minutes=closest_record['duration'])
  time_gap = date_time - closest_end_time
  return closest_record['topic'],closest_record['end_time'],time_gap.total_seconds()/60

def find_closest_record_after(host_id, df_combined, date_time, duration):
  if not isinstance(date_time, pd.Timestamp):
    date_time = pd.to_datetime(date_time)
  if df_combined['end_time'].dtype.tz is not None:
    date_time = date_time.tz_convert('UTC')  # or use tz_localize('UTC') if it does not has a timezone

  #print(f"Date time is {date_time} with type {type(date_time)}")
  #print(f"Start time type is {df_combined['start_time'].apply(type)}")
  df_filtered = df_combined[(df_combined['start_time'] >= date_time) & (df_combined['host_id'] == host_id)]
  if df_filtered.empty:
    return 'N.A.',None,14400
  closest_record = df_filtered.loc[df_filtered['start_time'].idxmin()]

  end_time = date_time+ pd.Timedelta(minutes=duration)
  time_gap = closest_record['start_time'] - end_time
  return closest_record['topic'],closest_record['start_time'],time_gap.total_seconds()/60

def convert_date_time_from_pacific_to_utc(d,t): 
  dt = datetime.combine(d, t)
  pacific = pytz.timezone('US/Pacific')
  pacific_time = pacific.localize(dt)
  utc_time = pacific_time.astimezone(pytz.utc)
  return utc_time

def convert_utc_to_pacific_display(utc_time):
    if pd.isna(utc_time):
        return None
    if utc_time.tzinfo is None:
        utc_time = pytz.utc.localize(utc_time)
    pacific = pytz.timezone('US/Pacific')
    pacific_time = utc_time.astimezone(pacific)
    formatted_pacific_time = pacific_time.strftime("%b %d, %I:%M %p")
    return formatted_pacific_time
   
def find_schedule(df_schedules,d,t,duration=60,w=0):
    dt = convert_date_time_from_pacific_to_utc(d+timedelta(weeks=w),t)
    st.sidebar.write(f"{duration} mins for {convert_utc_to_pacific_display(dt)}")

    df=df_schedules.copy()
    unique_hosts=df['host_id'].unique()
    #st.write(f"Unique hosts: {unique_hosts}")
    beforeList=[]
    afterList=[]
    for host in unique_hosts:
        t1,r1,g1=find_closest_record_before(host,df,dt,duration)
        t2,r2,g2=find_closest_record_after(host,df,dt,duration)
        beforeList.append({'host_id':host,'dt':dt,'duration':duration,
                       'topic':t1,'et':r1,'gap':g1,})
        afterList.append({'host_id':host,'dt':dt,'duration':duration,
                       'topic':t2,'st':r2,'gap':g2,})
    df_before=pd.DataFrame(beforeList)
    df_after=pd.DataFrame(afterList)
    return df_before,df_after

def main_api(date,time,duration,repeat):

  d=get_schedules()
  df_schedules=create_df(json.dumps(d))

  df_combined_before=pd.DataFrame()
  df_combined_after=pd.DataFrame()
  for i in range(repeat):
    df_before,df_after=find_schedule(df_schedules,date,time,duration,i)
    df_combined_before=pd.concat([df_combined_before,df_before], ignore_index=True)
    df_combined_after=pd.concat([df_combined_after,df_after], ignore_index=True)
  # Now combine
  idx_before=df_combined_before.groupby('host_id')['gap'].idxmin()
  df_min_before=df_combined_before.loc[idx_before]
  df_min_before=df_min_before.reset_index(drop=True)

  idx_after=df_combined_after.groupby('host_id')['gap'].idxmin()
  df_min_after=df_combined_after.loc[idx_after]
  df_min_after=df_min_after.reset_index(drop=True)

  df_min=pd.merge(df_min_before,df_min_after,on='host_id',suffixes=('_before','_after'))
  df_min['min_gap'] = df_min[['gap_before', 'gap_after']].min(axis=1)
  return df_min

def main():
  col1,col2,col3,col4=st.columns(4)
  date=col1.date_input("Find Zoom for: ", value=None)
  time=col2.time_input("Time (Pacific)", value=None)
  duration=col3.number_input("Duration", value=60)
  repeat=col4.number_input("Repeat", value=1)
  if date and time and duration and repeat:
    df_response=main_api(date,time,duration,repeat);
    # Display the results
    fields=['host_id','min_gap','gap_before','gap_after','topic_before','et','topic_after','st']
    df_display_new=df_response[fields].copy()
    df_display_new['et'] = df_display_new['et'].apply(convert_utc_to_pacific_display)
    df_display_new['st'] = df_display_new['st'].apply(convert_utc_to_pacific_display)
    df_display_new.sort_values(by='min_gap',ascending=False,inplace=True)
    df_display_new.rename(columns={'host_id':'Host','min_gap':'Minimum gap',
                                'topic_before':'Topic 1','et':'End time 1',
                                'topic_after':'Topic 2','st':'Start time 2',
                                },inplace=True)
    st.dataframe(df_display_new,hide_index=True)

main()