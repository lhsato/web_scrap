import pandas as pd 

provinces = ["Banteay Meanchey", "Battambang", "Kampong Cham", "Kampong Chhnang", "Kampong Speu", "Kampong Thom", "Kampot", "Kandal", "Kep", "Koh Kong", "Kratié", "Mondulkiri", "Oddar Meanchey", "Pailin", "Phnom Penh", "Preah Sihanouk", "Preah Vihear", "Prey Veng", "Pursat", "Ratanakiri", "Siem Reap", "Stung Treng", "Svay Rieng", "Takéo", "Tboung Khmum",]

populations = [898484,1132017,1062914,604895,924175,807254,682987,1352198,48772,140962,441078,93657,267703,79445,2352851,234702,249973,1277867,516072,235852,1099825,176488,613159,1097243,889970,
]

dict_provinces = {'Provinces':provinces, 'Population': populations}
df_provinces= pd.DataFrame.from_dict(dict_provinces)

df_provinces.to_csv('utils/provinces.csv')

# print(df_provinces)

# print(provinces[-25])

# for province in provinces:
#     if province == "Phnom Penh":
#         print(province)


with open('yuki.txt','+w') as file:
    file.write("add some text")