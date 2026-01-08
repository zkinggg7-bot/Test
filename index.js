const axios = require('axios');
const cheerio = require('cheerio');
const iconv = require('iconv-lite');

/**
 * إعدادات المحاكاة المتقدمة لجعل الطلب يبدو بشرياً قدر الإمكان
 * دون استهلاك موارد الذاكرة (بدون متصفح).
 */
const targetUrl = 'https://www.69shuba.com/txt/87906/39867326';

async function scrapeLightweight() {
    try {
        console.log(`[LOG] محاولة سحب "خفيفة" وذكية للفصل...`);

        // إنشاء جلسة مخصصة (Custom Session)
        const instance = axios.create({
            timeout: 20000,
            responseType: 'arraybuffer', // ضروري للتعامل مع ترميز GBK الصيني
            headers: {
                // ترتيب الـ Headers مهم جداً لبعض أنظمة الحماية
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                // إرسال كوكي أساسي يوحي بأننا قمنا بزيارة الموقع سابقاً
                'Cookie': 'zh_chosen=s; bcolor=; font=; size=; fontcolor=; width=;'
            }
        });

        // تنفيذ الطلب
        const response = await instance.get(targetUrl);

        // تحويل النص من ترميز GBK الصيني إلى UTF-8
        const decodedHtml = iconv.decode(response.data, 'gbk');
        const $ = cheerio.load(decodedHtml);

        // التحقق من الحظر (403 أو صفحة حماية)
        const title = $('h1').last().text().trim();
        if (!title || decodedHtml.includes('Cloudflare') || decodedHtml.includes('403 Forbidden')) {
            throw new Error('تم الحظر (403). الموقع يكتشف أنك تستخدم خادم Cloud.');
        }

        // تنظيف المحتوى (إزالة الإعلانات والنصوص المزعجة)
        $('.txtnav script, .txtnav .contentadv, .txtnav .txtinfo, .txtnav h1').remove();
        
        let content = $('.txtnav').text();
        
        // معالجة النصوص الصينية والمسافات
        content = content
            .replace(/\t/g, '')
            .replace(/\(本章完\)/g, '')
            .replace(/\n\s*\n/g, '\n\n')
            .trim();

        const nextUrl = $('.page1 a:contains("下一章")').attr('href') || 
                        $('.page1 a').last().attr('href');

        console.log(`[SUCCESS] تم جلب الفصل بنجاح: ${title}`);
        
        return {
            status: 'success',
            data: {
                title,
                nextChapter: nextUrl,
                content: content.substring(0, 500) + "..." // عينة من النص
            }
        };

    } catch (error) {
        let errorMessage = error.message;
        if (error.response && error.response.status === 403) {
            errorMessage = "خطأ 403: عنوان الـ IP الخاص بالخادم محظور تماماً من قبل الموقع.";
        }
        
        console.error(`[ERROR] ${errorMessage}`);
        return {
            status: 'error',
            message: errorMessage
        };
    }
}

// إعداد سيرفر بسيط للاستجابة
const http = require('http');
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');

    if (req.url === '/test') {
        const result = await scrapeLightweight();
        res.writeHead(200);
        res.end(JSON.stringify(result, null, 2));
    } else {
        res.writeHead(200);
        res.end(JSON.stringify({ 
            status: 'Lightweight Scraper Active',
            endpoint: '/test',
            note: 'This mode saves your Railway credits.'
        }));
    }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
