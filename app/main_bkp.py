import pandas as pd
from pathlib import Path

provinces = ["Banteay Meanchey", "Battambang", "Kampong Cham", "Kampong Chhnang", "Kampong Speu", "Kampong Thom", "Kampot", "Kandal", "Kep", "Koh Kong", "Kratié", "Mondulkiri", "Oddar Meanchey", "Pailin", "Phnom Penh", "Preah Sihanouk", "Preah Vihear", "Prey Veng", "Pursat", "Ratanakiri", "Siem Reap", "Stung Treng", "Svay Rieng", "Takéo", "Tboung Khmum",]


populations = [898484,1132017,1062914,604895,924175,807254,682987,1352198,48772,140962,441078,93657,267703,79445,2352851,234702,249973,1277867,516072,235852,1099825,176488,613159,1097243,889970,
]


dict_provinces = {'Provinces':provinces, 'Populations': populations}

df_provinces= pd.DataFrame.from_dict(dict_provinces)
print(df_provinces)

df_provinces.to_csv('provinces_yuki.csv', index=True)
try:
    df_provinces.to_csv('../utils/provinces_yuki.csv', index=False)  
except Exception as e:
    print("Error", e)
    # print("Directory 'utils' does not exist. Please create it and try again.")
# except (ValueError, TypeError, OSError) as e:
# except Exception as e:
#     print("Error", e)
# except FileNotFoundError:
#     print("Directory 'utils' does not exist. Please create it and try again.")
try:
    # Use absolute path or ensure directory exists
    output_path = Path(__file__).parent.parent / 'teste' / 'provinces_panha.csv'
    output_path.parent.mkdir(parents=False, exist_ok=False)
    df_provinces.to_csv(output_path, index=False)
# case 1
# except Exception as e:
#     print("Error", e.__class__)

# case 2
# except OSError:
#      print("Directory 'teste' already exists. Please remove it and try again.")

# case 3
except FileExistsError:
    print("Directory 'teste' already exists. Please remove it and try again.")


# print(df_provinces)

# print(provinces[-25])

# for province in provinces:
#     if province == "Phnom Penh":
#         print(province)

# case 5
# try:
#     with open('..\\vatey.csv','w') as file:
#         file.write(",Provinces,Population\n")
#         for i in range(len(provinces)):
#             file.write(str(i) + "," + provinces[i] + "," + str(populations[i]) + "\n") 

# except PermissionError:
#     print("Permission denied: Unable to write to 'vatey.csv'. Please check file permissions and try again.")       


# case 6
# open Vatey.cvs in Excel to show the error
# try to delete vatey.cvs from VS Code to see the error 
# the Error message is from the OS, not from Python, so we catch OSError instead of PermissionError or FileNotFoundError
try:
    file = open('..\\vatey.csv','w')
    file.write(",Provinces,Population\n")
    for i in range(len(provinces)):
        file.write(str(i) + "," + provinces[i] + "," + str(populations[i]) + "\n") 
    file.close()

# https://docs.python.org/3/library/exceptions.html
# case 7 specific error: good practice
except PermissionError:
    print("Permission denied: Unable to write to 'vatey.csv'. Please check file permissions and try again.")      

# # case 8: more general than PermissionError, but still specific to OS errors
# except OSError:
#     print("Permission denied: Unable to write to 'vatey.csv'. Please check file permissions and try again.")      


