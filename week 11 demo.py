# -*- coding: utf-8 -*-
"""
Created on Thu May  8 12:50:31 2025

@author: Thaliana Li
"""
import joblib

def week_11_demo(current_station, current_delay, target_station):
    
    knn_loaded = joblib.load('knn_model.pkl')
    
    iteration_times = target_station - current_station
    
    for i in range (iteration_times):
        prediction = knn_loaded.predict([[current_delay]])
        current_delay = prediction[0]
        current_station = current_station + 1
        print(f"Predicted delay at station {current_station} will be：{current_delay:.1f} minutes")
    #return current_delay


while True:
    current_station_input = int(input("Current station："))
    current_delay_input = int(input("Current delay in minutes："))
    target_station_input = int(input("Target station："))
    week_11_demo(current_station_input, current_delay_input, target_station_input)
    #print(result)
