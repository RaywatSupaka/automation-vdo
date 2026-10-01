const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync('browser_extension/content.js', 'utf8');
const start = source.indexOf('  const structuredProduct =');
const end = source.indexOf('  chrome.runtime.onMessage.addListener', start);
assert.ok(start > 0 && end > start);
const normalize = source.slice(source.indexOf('  const normalizedImageUrl ='), source.indexOf('  const idsFromUrl ='));
const code = normalize + '\n' + source.slice(start, end) + '\npageProduct()';

function scan({schema, meta = {}, matching, images = ['https://img.susercontent.com/file/a']}) {
  const canonical = 'https://shopee.co.th/product/11/22';
  const selectors = {
    'link[rel="canonical"]': {href: canonical},
    'meta[property="og:image"]': {content: images[0]},
    h1: {textContent: 'ชุดน้ำพริกข้าวซอย'},
    ...Object.fromEntries(Object.entries(meta).map(([key, value]) => [key, {content: value}]))
  };
  const ctx = vm.createContext({URL,
    document: {title: 'Shopee', querySelector: key => selectors[key] || null,
      querySelectorAll: key => key === 'script[type="application/ld+json"]' && schema ? [{textContent: JSON.stringify(schema)}] : []},
    location: {href: canonical}, state: {products: new Map(matching ? [['x', matching]] : [])},
    idsFromUrl: url => {const found = String(url).match(/product\/(\d+)\/(\d+)/); return found ? {shop_id:found[1],product_id:found[2]} : {shop_id:'',product_id:''};},
    clean: text => String(text || '').trim().replace(/\s+/g, ' '),
    pickText: (root, keys) => keys.map(key => root.querySelector(key)).map(node => node?.content || node?.textContent || '').find(Boolean) || '',
    productImages: () => images,
  });
  return vm.runInContext(code, ctx);
}

const result = scan({schema: {'@type': 'Product', name:'ชุดน้ำพริกข้าวซอย',
  description:'เส้นข้าวซอยพร้อมน้ำพริก', offers:{price:'199'},
  image:['https://img.susercontent.com/file/b']}});
assert.equal(result.description, 'เส้นข้าวซอยพร้อมน้ำพริก');
assert.equal(result.price, '199');
assert.equal(result.images.length, 2);

const fallback = scan({matching:{product_id:'22',shop_id:'11',product_name:'ชื่อจากการ์ด',
  description:'ข้อความในการ์ด',price:'89'}});
assert.equal(fallback.description, 'ข้อความในการ์ด');
assert.equal(fallback.price, '89');

const wrong = scan({schema:{'@type':'Product',url:'https://shopee.co.th/product/11/99',
  description:'สินค้าอื่น', offers:{price:'999'}}});
assert.notEqual(wrong.description, 'สินค้าอื่น');
assert.notEqual(wrong.price, '999');
assert.equal(scan({images:[]}).images.length, 0, 'blank og:image must not become the product page URL');
console.log('Shopee product metadata 421: structured, card fallback and wrong-product guard passed');
