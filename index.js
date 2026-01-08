const axios = require('axios');
const cheerio = require('cheerio');
const iconv = require('iconv-lite');

const targetUrl = 'https://www.69shuba.com/txt/87906/39867326';

async function scrapeWithRealCookies() {
    try {
        console.log(`[LOG] محاولة السحب باستخدام كوكيز حقيقي مستخرج من الصور...`);

        // ملاحظة: قمت بنسخ القيم الظاهرة في لقطات الشاشة الخاصة بك
        const cookieString = [
            'zh_choose=s',
            'shuba=10814-11633-20856-3178',
            'jieqiHistory=87906-39867326-%25u7B2C1%25u7AE0%2520%25u674E%25u6155%25u751F-1767886344',
            '_ga=GA1.1.2076534855.1767884557',
            '_sharedID=3801fe8a-709a-49e0-a6c8-dde12225ee31'
        ].join('; ');

        const instance = axios.create({
            timeout: 15000,
            responseType: 'arraybuffer',
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Cookie': cookieString, // الكوكيز الحقيقي الخاص بك
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://www.69shuba.com/',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        });

        const response = await instance.get(targetUrl);
        const decodedHtml = iconv.decode(response.data, 'gbk');
        const $ = cheerio.load(decodedHtml);

        // التحقق من النجاح
        const title = $('h1').last().text().trim();
        
        if (!title || decodedHtml.includes('403 Forbidden')) {
            throw new Error('حتى مع الكوكيز الحقيقي، الموقع يرفض الـ IP الخاص بالخادم.');
        }

        // تنظيف المحتوى
        $('.txtnav script, .txtnav .contentadv, .txtnav .txtinfo, .txtnav h1').remove();
        let content = $('.txtnav').text();
        content = content.replace(/\(本章完\)/g, '').replace(/\n\s*\n/g, '\n\n').trim();

        const nextUrl = $('.page1 a:contains("下一章")').attr('href') || $('.page1 a').last().attr('href');

        console.log(`[SUCCESS] نجحت الخطة! الفصل المجلوب: ${title}`);
        
        return {
            status: 'success',
            title,
            nextChapter: nextUrl,
            content: content.substring(0, 500) + "..."
        };

    } catch (error) {
        console.error(`[ERROR] ${error.message}`);
        return { status: 'error', message: error.message };
    }
}

const http = require('http');
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (req.url === '/test') {
        const result = await scrapeWithRealCookies();
        res.end(JSON.stringify(result, null, 2));
    } else {
        res.end(JSON.stringify({ message: 'Scraper with Real Cookies is Online', endpoint: '/test' }));
    }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server started on port ${PORT}`);
});
