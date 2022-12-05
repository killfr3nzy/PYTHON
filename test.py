import requests
import json

from aiogram.types import message

from config import headers, cookies
import os
import math


def get_data():
    params = {
        'topArea': '2',
        'area': '4',
        'city': '7900',
        'rooms': '2-3.5',
        'Order': '3',
        'priceOnly': '1',
        'imgOnly': '1',
        # 'page': pages,
    }

    if not os.path.exists('data'):
        os.mkdir('data')

    s = requests.Session()
    response = s.get('https://gw.yad2.co.il/feed-search-legacy/realestate/rent', params=params, cookies=cookies, headers=headers).json()

    total_items = response.get('data').get('feed').get('total_items')

    if total_items is None:
        return f'[!] No items!'

    pages_count = math.ceil(total_items / 36)
    # print(f'[INFO] Total apartments: {total_items} | Total pages: {pages_count}')

    dirot = response.get('data').get('feed').get('feed_items')

    with open('data/dirot.json', 'w', encoding="utf-8") as file:
        json.dump(dirot, file, indent=4, ensure_ascii=False)

    dirot_filtered = {}

    for i in range(pages_count):
        pages = f'{i + 1}'

        params = {
            'topArea': '2',
            'area': '4',
            'city': '7900',
            'rooms': '2-3.5',
            'price': '-1-3800',
            'Order': '3',
            'priceOnly': '1',
            'imgOnly': '1',
            'page': pages,
        }

        response = s.get('https://gw.yad2.co.il/feed-search-legacy/realestate/rent', params=params, cookies=cookies,
                         headers=headers).json()

        dirot = response.get('data').get('feed').get('feed_items')

        for dira in dirot:
            feed_source = dira.get('feed_source')
            if feed_source == 'commercial':
                continue
            dira_id = dira.get('id')
            if dira_id is None:
                continue
            address = dira.get('row_1')
            price = dira.get('price')
            text = dira.get('search_text')
            dira_info = dira.get('row_3')
            add_date = dira.get('date')
            # images = dira.get('images')
            location = dira.get('coordinates')

            dirot_filtered[dira_id] = {
                'add_date': add_date,
                'address': address,
                'price': price,
                'text': text,
                'info': dira_info,
                # 'images': images,
                'coordinates': location,
                'feed_source': feed_source,
                'dira_url': ('https://www.yad2.co.il/item/' + str(dira_id))
            }

        print(f'[+] Finished {i + 1} of the {pages_count} pages')
    print('[INFO] Total apartments: ' + str(len(dirot_filtered)))

    with open('data/filtered_data.json', 'w', encoding="utf-8") as file:
        json.dump(dirot_filtered, file, indent=4, ensure_ascii=False)


def main():
    get_data()


if __name__ == '__main__':
    main()
