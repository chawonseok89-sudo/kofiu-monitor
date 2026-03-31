
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today, un_info, limit_date, LIMIT_URL)
            )
        else:
            messages.append(
                "[{}] 금융거래등제한대상자 명단 변동없음\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, un_info, limit_date, LIMIT_URL)
            )

    # ② 공고/고시/훈령/예규 모니터링
    announce_hash, posts, latest_date = get_announce_info()

    if announce_hash:
        new_hashes["announce"] = announce_hash
        last_announce = last_hashes.get("announce")
        latest_post = posts[0] if posts else None

        if last_announce is None:
            post_info = "게시글 확인 불가"
            if latest_post:
                post_info = "최신 게시글: {} ({})\n링크: {}".format(
                    latest_post["title"], latest_post["date"], latest_post["link"])
            messages.append(
                "[koFIU 공고/고시/훈령/예규 모니터링 시작]\n\n"
                "{}\n\n"
                "전체 목록: {}".format(post_info, ANNOUNCE_URL)
            )
        elif announce_hash != last_announce:
            post_info = "게시글 확인 불가"
            if latest_post:
                post_info = "업데이트 게시글: {} ({})\n링크: {}".format(
                    latest_post["title"], latest_post["date"], latest_post["link"])
            messages.append(
                "[긴급] 공고/고시/훈령/예규 업데이트!\n\n"
                "감지일: {}\n\n"
                "{}\n\n"
                "전체 목록: {}\n\n"
                "즉시 확인해 주세요!".format(today, post_info, ANNOUNCE_URL)
            )
        else:
            post_info = "게시글 확인 불가"
            if latest_post:
                post_info = "최신 게시글: {} ({})\n링크: {}".format(
                    latest_post["title"], latest_post["date"], latest_post["link"])
            messages.append(
                "[{}] 공고/고시/훈령/예규 변동없음\n\n"
                "{}\n\n"
                "전체 목록: {}".format(today, post_info, ANNOUNCE_URL)
            )

    print("전송할 메시지 수: {}".format(len(messages)))

    if messages:
        full_message = "\n\n========================================\n\n".join(messages)
        send_telegram(full_message)

    if new_hashes:
        merged = last_hashes.copy()
        merged.update(new_hashes)
        save_hashes(merged)

    print("=== 모니터링 완료 ===")


if __name__ == "__main__":
    main()
