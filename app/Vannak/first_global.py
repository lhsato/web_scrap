from bs4 import BeautifulSoup
import pandas as pd
import os

def scrape_robotics_results():
    # 1. Path to your saved HTML file
    file_path = 'results.html'
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found. Please make sure the HTML is saved in this folder.")
        return

    # 2. Load the HTML file
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')

    # 3. Find the main container (MuiPaper)
    main_paper = soup.find('div', class_='css-1usr5cm')
    
    if not main_paper:
        print("Could not find the 'css-1usr5cm' div.")

    # 4. Find the Tab Panel containing the data
    tab_panel = main_paper.find('div', class_='css-iescws')

    if not tab_panel:
        print("Could not find the 'css-iescws' div inside the paper.")
        return

    # 5. Extract rows using the Grid layout structure
    all_data = []
    rows = tab_panel.find_all('div', class_='MuiGrid-container')

    for row in rows:
        cells = row.find_all('div', class_='MuiGrid-item')
    
        row_values = [cell.get_text(strip=True) for cell in cells]
        
        if row_values:
            all_data.append(row_values)

    # 6. Save to CSV using Pandas
    if all_data:
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        
        output_file = 'robotics_finals_scraped.csv'
        df.to_csv(output_file, index=False)
        
        print("SUCCESS!")
        print(f"Scraped {len(df)} alliance rankings.")
        print(f"File saved to: {output_file}")
        print(df)
    else:
        print("No data found inside the grid.")

if __name__ == "__main__":
    scrape_robotics_results()