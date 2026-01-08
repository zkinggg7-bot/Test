const axios = require('axios');
const cheerio = require('cheerio');
const iconv = require('iconv-lite');

// الرابط المستهدف
const targetUrl = 'https://www.69shuba.com/txt/87906/39867326';

async function scrapeChapter() {
    try {
        console.log(`جاري جلب الفصل من: ${targetUrl}...`);

        const response = await axios.get(targetUrl, {
            responseType: 'arraybuffer',
            timeout: 10000, // مهلة 10 ثواني
            headers: {
                // تحديث الـ Headers لمحاكاة متصفح حقيقي بشكل أفضل
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.69shuba.com/',
                'Connection': 'keep-alive',
                'Cache-Control': 'max-age=0'
            }
        });

        const html = iconv.decode(response.data, 'gbk');
        const $ = cheerio.load(html);

        // استخراج العنوان
        const title = $('h1').text().trim() || 'لم يتم العثور على عنوان';

        // تنظيف المحتوى
        $('.txtnav .contentadv').remove();
        $('.txtnav script').remove();
        $('.txtnav h1').remove();
        $('.txtnav .txtinfo').remove();

        let content = $('.txtnav').text();
        content = content.replace(/\(本章完\)/g, '')
                        .replace(/\n\s*\n/g, '\n\n')
                        .trim();

        const nextChapterUrl = $('.page1 a').last().attr('href');

        const result = {
            success: true,
            title,
            nextChapterUrl,
            contentSnippet: content.substring(0, 300) + '...'
        };

        console.log('✅ تم السحب بنجاح!');
        return result;

    } catch (error) {
        console.error('❌ حدث خطأ أثناء السحب:', error.message);
        return {
            success: false,
            error: error.message,
            tip: 'قد يكون الموقع قد حظر عنوان IP الخادم، جرب التشغيل محلياً أو استخدام Proxy.'
        };
    }
}

// إعداد السيرفر
const http = require('http');
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    
    if (req.url === '/test') {
        const data = await scrapeChapter();
        res.writeHead(200);
        res.end(JSON.stringify(data, null, 2));
    } else {
        res.writeHead(200);
        res.end(JSON.stringify({ message: 'خادم السحب يعمل. اذهب إلى /test' }));
    }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
